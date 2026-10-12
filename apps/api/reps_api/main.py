"""Reps API.

Public routes (/api/...) never return answer keys, hidden tests, or reference code.
Internal routes (/internal/...) are for the background worker and evaluation scripts
and require the INTERNAL_API_TOKEN header.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import time
import uuid
from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .content.seed_coding import SEED_PROBLEMS
from .ingest.pdf import MAX_BYTES, ExtractionError, extract_pdf
from .tutor.knowledge_tracing import MODEL_VERSION, BossPolicy, TopicMastery, boss_hp
from .verification.coding_engine import (
    CodingProblemSpec,
    CodingVerification,
    SubmissionResult,
    TestCase,
    grade_submission,
    verify_coding_problem,
)
from .verification.executors import executor_from_env
from .verification.math_engine import (
    GradeResult,
    MathProblemSpec,
    MathTask,
    MathVerification,
    grade_answer,
    verify_problem,
)
from .verification.status import VerificationStatus
from .verification.timeouts import VerificationTimeout, run_with_timeout

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("reps.api")

app = FastAPI(title="Reps API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("WEB_ORIGINS", "http://localhost:3000").split(",") if o],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    log.info("%s %s %s %dms rid=%s", request.method, request.url.path, response.status_code, (time.perf_counter() - started) * 1000, rid)
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": {"code": "internal", "message": "Something broke on our side."}})


def require_internal(x_internal_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("INTERNAL_API_TOKEN")
    if not expected:
        raise HTTPException(503, detail="INTERNAL_API_TOKEN is not configured")
    if not x_internal_token or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(401, detail="bad internal token")


# ---------------------------------------------------------------- health


@app.get("/health")
def health() -> dict[str, Any]:
    executor = executor_from_env()
    return {
        "ok": True,
        "env": os.environ.get("REPS_ENV", "development"),
        "integrations": {
            "code_runner": executor.name,
            "code_runner_is_sandbox": executor.name == "judge0",
            "supabase": bool(os.environ.get("SUPABASE_URL")),
            "llm": bool(os.environ.get("LLM_API_KEY")),
        },
        "bkt_model": MODEL_VERSION,
    }


# ---------------------------------------------------------------- math (internal)


class VerifyMathRequest(BaseModel):
    spec: MathProblemSpec
    seed: int = Field(ge=0, le=2**31)


@app.post("/internal/verify/math", dependencies=[Depends(require_internal)])
def verify_math(req: VerifyMathRequest) -> MathVerification:
    try:
        return run_with_timeout(verify_problem, req.spec, req.seed, timeout_s=15)
    except VerificationTimeout:
        return MathVerification(status=VerificationStatus.REJECTED, reason="verification timed out after 15s")


class GradeMathRequest(BaseModel):
    task: MathTask
    answer_key: str
    student_answer: str = Field(max_length=300)


@app.post("/internal/grade/math", dependencies=[Depends(require_internal)])
def grade_math(req: GradeMathRequest) -> GradeResult:
    try:
        return run_with_timeout(grade_answer, req.task, req.answer_key, req.student_answer, timeout_s=8)
    except VerificationTimeout:
        return GradeResult(correct=None, status="unparseable", method="timeout", detail="grading timed out")


@app.post("/internal/verify/coding", dependencies=[Depends(require_internal)])
def verify_coding(spec: CodingProblemSpec) -> CodingVerification:
    result = verify_coding_problem(spec, executor_from_env())
    result.tests = []  # stored by the worker, not returned over HTTP
    return result


# ---------------------------------------------------------------- documents


class ExtractionPreview(BaseModel):
    filename: str
    page_count: int
    text_pages: int
    char_count: int
    chunk_count: int
    preview: list[dict[str, Any]]


@app.post("/api/documents/extract")
async def extract_document(file: UploadFile = File(...)) -> ExtractionPreview:
    data = await file.read(MAX_BYTES + 1)
    try:
        result = extract_pdf(data)
    except ExtractionError as err:
        raise HTTPException(422, detail=str(err)) from err
    return ExtractionPreview(
        filename=re.sub(r"[^\w.\- ]", "_", file.filename or "upload.pdf")[:120],
        page_count=result.page_count,
        text_pages=result.text_pages,
        char_count=result.char_count,
        chunk_count=len(result.chunks),
        preview=[{"pages": [c.page_start, c.page_end], "text": c.text[:400]} for c in result.chunks[:3]],
    )


# ---------------------------------------------------------------- coding arena


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


@lru_cache(maxsize=1)
def _arena() -> dict[str, tuple[CodingProblemSpec, CodingVerification]]:
    """Verify the seed set once per process. Only verified problems are served.
    (Moves to the coding_problems tables once Supabase is connected.)"""
    executor = executor_from_env()
    arena = {}
    for spec in SEED_PROBLEMS:
        verification = verify_coding_problem(spec, executor)
        if verification.status is VerificationStatus.VERIFIED:
            arena[_slug(spec.title)] = (spec, verification)
        else:
            log.error("seed problem %s failed verification: %s", spec.title, verification.reason)
    return arena


class ProblemSummary(BaseModel):
    slug: str
    title: str
    pattern: str
    difficulty: str


class ProblemDetail(ProblemSummary):
    statement: str
    signature: str
    examples: list[dict[str, Any]]
    verification: dict[str, Any]


@app.get("/api/coding/problems")
def list_problems() -> list[ProblemSummary]:
    return [ProblemSummary(slug=s, title=p.title, pattern=p.pattern, difficulty=p.difficulty) for s, (p, _) in _arena().items()]


@app.get("/api/coding/problems/{slug}")
def get_problem(slug: str) -> ProblemDetail:
    spec, ver = _problem(slug)
    examples = [{"args": t.args, "expected": t.expected} for t in ver.tests if not t.hidden]
    return ProblemDetail(
        slug=slug,
        title=spec.title,
        pattern=spec.pattern,
        difficulty=spec.difficulty,
        statement=spec.statement,
        signature=spec.signature,
        examples=examples,
        verification={"cases_run": ver.cases_run, "method": "reference vs brute force", "executor": ver.executor},
    )


class CodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50_000)
    language: str = "python"


def _problem(slug: str) -> tuple[CodingProblemSpec, CodingVerification]:
    arena = _arena()
    if slug not in arena:
        raise HTTPException(404, detail="problem not found")
    return arena[slug]


def _grade(slug: str, req: CodeRequest, include_hidden: bool) -> SubmissionResult:
    if req.language != "python":
        raise HTTPException(422, detail="Only Python is supported right now.")
    spec, ver = _problem(slug)
    tests: list[TestCase] = ver.tests
    return grade_submission(req.code, tests, executor_from_env(), include_hidden=include_hidden, unordered=spec.unordered_output)


@app.post("/api/coding/problems/{slug}/run")
def run_code(slug: str, req: CodeRequest) -> SubmissionResult:
    return _grade(slug, req, include_hidden=False)


@app.post("/api/coding/problems/{slug}/submit")
def submit_code(slug: str, req: CodeRequest) -> SubmissionResult:
    return _grade(slug, req, include_hidden=True)


# ---------------------------------------------------------------- boss preview


class BossState(BaseModel):
    topics: list[dict[str, Any]]
    recent: list[str] = Field(default_factory=list, max_length=50)


@app.post("/api/boss/next")
def boss_next(state: BossState) -> dict[str, Any]:
    """Stateless preview of the boss policy (persistence arrives with Supabase)."""
    topics = [TopicMastery(**t) for t in state.topics]
    if not topics:
        raise HTTPException(422, detail="no topics")
    return {"next_topic": BossPolicy().next_topic(topics, state.recent), "hp": boss_hp(topics), "model": MODEL_VERSION}
