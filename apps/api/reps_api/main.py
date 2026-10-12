"""Reps API.

Public routes (/api/...) never return answer keys before an attempt, hidden tests,
or reference code. Internal routes (/internal/...) are for workers and evaluation
scripts and require the INTERNAL_API_TOKEN header.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import arena, exam, generation, interview, player
from .ingest.pdf import MAX_BYTES, ExtractionError, extract_pdf
from .llm import llm_from_env
from .store import get_store
from .tutor.knowledge_tracing import MODEL_VERSION
from .verification.coding_engine import CodingProblemSpec, CodingVerification, verify_coding_problem
from .verification.executors import executor_from_env
from .verification.math_engine import GradeResult, MathProblemSpec, MathTask, MathVerification, grade_answer, verify_problem
from .verification.safe_math import DEFAULT_VARIABLES, UnsupportedExpression, parse_math
from .verification.status import VerificationStatus
from .verification.timeouts import VerificationTimeout, run_with_timeout

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("reps.api")


def _warm_up() -> None:
    """Start the verification workers and verify the Arena so the first request is fast."""
    try:
        run_with_timeout(parse_math, "x", timeout_s=60)
        arena.load(get_store())
    except Exception:  # warm-up is best effort; real requests report their own errors
        log.exception("warm-up failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    exam.sync_builtin_courses(get_store())
    if os.environ.get("REPS_SKIP_WARMUP") != "1":
        threading.Thread(target=_warm_up, name="warm-up", daemon=True).start()
    yield


app = FastAPI(title="Reps API", version="0.2.0", lifespan=lifespan)
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


@app.exception_handler(exam.ExamError)
@app.exception_handler(arena.ArenaError)
@app.exception_handler(interview.InterviewError)
async def domain_error(request: Request, exc: Exception):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})  # type: ignore[attr-defined]


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something broke on our side. Check the API window for the error."})


def require_internal(x_internal_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("INTERNAL_API_TOKEN")
    if not expected:
        raise HTTPException(503, detail="INTERNAL_API_TOKEN is not configured")
    if not x_internal_token or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(401, detail="bad internal token")


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, detail=f"Files must be under {MAX_BYTES // (1024 * 1024)} MB.")
    return data


# ---------------------------------------------------------------- health


@app.get("/health")
def health() -> dict[str, Any]:
    executor = executor_from_env()
    llm = llm_from_env()
    return {
        "ok": True,
        "env": os.environ.get("REPS_ENV", "development"),
        "mode": "local",
        "integrations": {
            "code_runner": executor.name,
            "code_runner_is_sandbox": executor.name == "judge0",
            "llm": f"{llm.name}:{llm.model}" if llm else None,
            "supabase": bool(os.environ.get("SUPABASE_URL")),
        },
        "bkt_model": MODEL_VERSION,
    }


# ---------------------------------------------------------------- player


@app.get("/api/player")
def get_player() -> dict[str, Any]:
    return player.summary(get_store())


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


@app.post("/api/player/name")
def rename_player(body: RenameIn) -> dict[str, Any]:
    return player.rename(get_store(), body.name)


@app.get("/api/telemetry/verification")
def verification_telemetry() -> dict[str, Any]:
    store = get_store()
    rows = store.all("select subject, status, count(*) n, avg(duration_ms) ms from verification_log group by subject, status")
    reasons = store.all("select subject, reason, count(*) n from verification_log where status != 'verified' group by subject, reason order by n desc limit 20")
    return {"counts": rows, "rejection_reasons": reasons}


# ---------------------------------------------------------------- exam mode


@app.get("/api/exam/courses")
def courses() -> list[dict[str, Any]]:
    return exam.list_courses(get_store())


@app.post("/api/exam/courses/upload")
async def upload_course(file: UploadFile = File(...), name: str = Form(..., min_length=1, max_length=80)) -> dict[str, Any]:
    data = await _read_upload(file)
    try:
        extraction = extract_pdf(data)
    except ExtractionError as err:
        raise HTTPException(422, detail=str(err)) from err
    preview = {
        "filename": re.sub(r"[^\w.\- ]", "_", file.filename or "upload.pdf")[:120],
        "page_count": extraction.page_count,
        "char_count": extraction.char_count,
        "chunks": len(extraction.chunks),
        "sample": [{"pages": [c.page_start, c.page_end], "text": c.text[:280]} for c in extraction.chunks[:2]],
    }
    provider = llm_from_env()
    if provider is None:
        return {
            "preview": preview,
            "ai_available": False,
            "job": None,
            "message": "Text extracted. Turning it into questions needs an AI key (LLM_API_KEY and LLM_MODEL in .env). The built-in courses work without one.",
        }
    job = generation.start_job(get_store(), provider, name.strip(), preview["filename"], extraction)
    return {"preview": preview, "ai_available": True, "job": job, "message": "Building your boss."}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    job = generation.job_view(get_store(), job_id)
    if not job:
        raise HTTPException(404, detail="Job not found.")
    return job


class StartExam(BaseModel):
    course_id: str
    length: int = Field(default=exam.DEFAULT_LENGTH, ge=5, le=30)


@app.post("/api/exam/sessions")
def start_exam(body: StartExam) -> dict[str, Any]:
    return exam.start_session(get_store(), body.course_id, body.length)


@app.get("/api/exam/sessions/{session_id}")
def exam_state(session_id: str) -> dict[str, Any]:
    return exam.session_state(get_store(), session_id)


@app.post("/api/exam/sessions/{session_id}/next")
def exam_next(session_id: str) -> dict[str, Any]:
    return exam.next_question(get_store(), session_id)


class QuestionRef(BaseModel):
    question_id: str


@app.post("/api/exam/sessions/{session_id}/hint")
def exam_hint(session_id: str, body: QuestionRef) -> dict[str, Any]:
    return exam.use_hint(get_store(), session_id, body.question_id)


class ExamAnswer(BaseModel):
    question_id: str
    answer: str = Field(max_length=300)


@app.post("/api/exam/sessions/{session_id}/answer")
def exam_answer(session_id: str, body: ExamAnswer) -> dict[str, Any]:
    return exam.submit_answer(get_store(), session_id, body.question_id, body.answer)


@app.post("/api/exam/sessions/{session_id}/retreat")
def exam_retreat(session_id: str) -> dict[str, Any]:
    return exam.retreat(get_store(), session_id)


@app.get("/api/exam/sessions/{session_id}/results")
def exam_results(session_id: str) -> dict[str, Any]:
    return exam.results(get_store(), session_id)


class PreviewIn(BaseModel):
    text: str = Field(max_length=300)


@app.post("/api/math/preview")
def math_preview(body: PreviewIn) -> dict[str, Any]:
    """Show the student how their typed answer was read, before they submit."""
    import sympy as sp

    if not body.text.strip():
        return {"latex": None, "error": None}
    try:
        parts = [p for p in re.split(r",|\bor\b", body.text) if p.strip()]
        rendered = []
        for p in parts[:6]:
            p = re.sub(r"^\s*x\s*=", "", p)
            rendered.append(sp.latex(parse_math(p, DEFAULT_VARIABLES)))
        return {"latex": ",\\; ".join(rendered), "error": None}
    except UnsupportedExpression as err:
        return {"latex": None, "error": str(err)}


# ---------------------------------------------------------------- coding arena


@app.get("/api/coding/problems")
def list_problems() -> list[dict[str, Any]]:
    return arena.list_problems(get_store())


@app.get("/api/coding/problems/{slug}")
def get_problem(slug: str) -> dict[str, Any]:
    return arena.problem_detail(get_store(), slug)


class CodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50_000)
    language: str = "python"


@app.post("/api/coding/problems/{slug}/run")
def run_code(slug: str, req: CodeRequest) -> dict[str, Any]:
    return arena.grade(get_store(), slug, req.code, req.language, submit=False)


@app.post("/api/coding/problems/{slug}/submit")
def submit_code(slug: str, req: CodeRequest) -> dict[str, Any]:
    return arena.grade(get_store(), slug, req.code, req.language, submit=True)


# ---------------------------------------------------------------- interview mode


@app.post("/api/interview/resume")
async def upload_resume(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await _read_upload(file)
    return interview.upload_resume(get_store(), file.filename or "resume.pdf", data)


@app.get("/api/interview/resume/latest")
def latest_resume() -> dict[str, Any] | None:
    return interview.latest_resume(get_store())


@app.get("/api/interview/sessions")
def interview_history() -> list[dict[str, Any]]:
    return get_store().all(
        "select s.id, s.role, s.kind, s.status, s.started_at, s.completed_at, count(t.id) answers from interview_sessions s "
        "left join interview_turns t on t.session_id = s.id group by s.id order by s.started_at desc limit 20"
    )


@app.post("/api/interview/sessions")
def start_interview(body: interview.StartInterview) -> dict[str, Any]:
    return interview.start(get_store(), body)


@app.get("/api/interview/sessions/{session_id}")
def interview_state(session_id: str) -> dict[str, Any]:
    return interview.state(get_store(), session_id)


@app.post("/api/interview/sessions/{session_id}/answer")
def interview_answer(session_id: str, body: interview.AnswerIn) -> dict[str, Any]:
    return interview.submit(get_store(), session_id, body)


@app.post("/api/interview/sessions/{session_id}/finish")
def interview_finish(session_id: str) -> dict[str, Any]:
    return interview.finish(get_store(), session_id)


@app.get("/api/interview/sessions/{session_id}/report")
def interview_report(session_id: str) -> dict[str, Any]:
    return interview.report(get_store(), session_id)


# ---------------------------------------------------------------- internal


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
    result.tests = []
    return result
