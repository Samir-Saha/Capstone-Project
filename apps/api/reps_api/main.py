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

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import achievements, arena, exam, generation, interview, party, player, progress
from .ingest.office import extract_docx, extract_pptx
from .ingest.pdf import MAX_BYTES, ExtractionError, combine, extract_pdf, extract_text
from .llm import llm_from_env
from .store import get_store
from .tutor.knowledge_tracing import MODEL_VERSION
from .verification.coding_engine import CodingProblemSpec, CodingVerification, verify_coding_problem
from .verification.executors import executor_from_env
from .verification.math_engine import GradeResult, MathProblemSpec, MathTask, MathVerification, grade_answer, verify_problem
from .verification.safe_math import DEFAULT_VARIABLES, UnsupportedExpression, parse_math, to_latex
from .verification.status import VerificationStatus
from .verification.timeouts import VerificationTimeout, run_with_timeout

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("reps.api")
MAX_UPLOAD_FILES = 30


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
@app.exception_handler(party.PartyError)
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


@app.get("/api/progress")
def get_progress() -> dict[str, Any]:
    return progress.summary(get_store())


@app.get("/api/achievements")
def list_achievements() -> list[dict[str, Any]]:
    achievements.check(get_store())
    return achievements.listing(get_store())


class SeenIn(BaseModel):
    keys: list[str] = Field(max_length=50)


@app.post("/api/achievements/seen")
def achievements_seen(body: SeenIn) -> dict[str, bool]:
    achievements.mark_seen(get_store(), body.keys)
    return {"ok": True}


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
async def upload_course(
    files: list[UploadFile] | None = File(None),
    name: str = Form(..., min_length=1, max_length=80),
    text: str = Form(""),
) -> dict[str, Any]:
    """PDFs, .txt/.md files and pasted notes, any mix, into one course."""
    files = files or []
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(413, detail=f"Up to {MAX_UPLOAD_FILES} files at a time.")
    named = []
    skipped: list[dict[str, str]] = []
    for f in files:
        fname = re.sub(r"[^\w.\- ]", "_", f.filename or "upload.pdf")[:120]
        data = await _read_upload(f)
        low = fname.lower()
        try:
            if low.endswith((".txt", ".md", ".markdown")):
                named.append((fname, extract_text(data.decode("utf-8", errors="replace"))))
            elif low.endswith(".docx"):
                named.append((fname, extract_docx(data)))
            elif low.endswith(".pptx"):
                named.append((fname, extract_pptx(data)))
            else:
                named.append((fname, extract_pdf(data)))
        except ExtractionError as err:
            skipped.append({"name": fname, "reason": str(err)})
    if text.strip():
        try:
            named.append(("Pasted notes", extract_text(text[:400_000])))
        except ExtractionError as err:
            skipped.append({"name": "Pasted notes", "reason": str(err)})
    if not named:
        if skipped:
            raise HTTPException(422, detail="; ".join(f"{s['name']}: {s['reason']}" for s in skipped))
        raise HTTPException(422, detail="Add a file or paste some notes first.")
    extraction = combine(named)
    preview = {
        "filename": named[0][0] if len(named) == 1 else f"{len(named)} sources",
        "files": [{"name": n, "pages": ex.page_count} for n, ex in named],
        "skipped": skipped,
        "page_count": extraction.page_count,
        "char_count": extraction.char_count,
        "chunks": len(extraction.chunks),
        "sample": [{"pages": [c.page_start, c.page_end], "text": c.text[:280]} for c in extraction.chunks[:2]],
    }
    provider = llm_from_env()
    job = generation.start_job(get_store(), provider, name.strip(), preview["filename"], extraction)
    return {
        "preview": preview,
        "ai_available": provider is not None,
        "job": job,
        "message": "Building your boss." if provider else "Building your boss from your notes. No AI key is set, so questions come straight from your text.",
    }


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
    answer: str = Field(default="", max_length=300)
    steps: list[str] | None = Field(default=None, max_length=20)


@app.post("/api/exam/sessions/{session_id}/answer")
def exam_answer(session_id: str, body: ExamAnswer) -> dict[str, Any]:
    steps = [s[:300] for s in body.steps] if body.steps else None
    return exam.submit_answer(get_store(), session_id, body.question_id, body.answer, steps=steps)


@app.get("/api/raid")
def raid_preview() -> dict[str, Any]:
    return exam.raid_preview(get_store())


@app.post("/api/raid")
def raid_start() -> dict[str, Any]:
    return exam.start_raid(get_store())


# ---------------------------------------------------------------- party raids
# Async routes: rooms live in the event loop, so every change to them happens there.


class PartyCreate(BaseModel):
    course_id: str
    name: str = Field(min_length=1, max_length=40)


class PartyJoin(BaseModel):
    name: str = Field(min_length=1, max_length=40)


@app.post("/api/party")
async def party_create(body: PartyCreate) -> dict[str, Any]:
    store = get_store()
    # Local mode: the creator is the person running Reps, so their answers count here.
    return party.HUB.create(store, body.course_id, body.name, player_store=store)


@app.get("/api/party/network")
async def party_network() -> dict[str, Any]:
    return {"addresses": party.lan_addresses()}


@app.get("/api/party/{code}")
async def party_preview(code: str) -> dict[str, Any]:
    return party.HUB.preview(code)


@app.post("/api/party/{code}/join")
async def party_join(code: str, body: PartyJoin) -> dict[str, Any]:
    return party.HUB.join(code, body.name, player_store=None)


@app.websocket("/api/party/{code}/ws")
async def party_socket(ws: WebSocket, code: str, token: str = "") -> None:
    try:
        room = party.HUB.room(code)
        member = party.HUB.player_for(room, token)
    except party.PartyError as exc:
        await ws.accept()
        await ws.send_json({"type": "error", "fatal": True, "message": exc.message})
        await ws.close(code=4404 if exc.status == 404 else 4403)
        return
    await ws.accept()
    await party.HUB.connect(room, member, ws)
    try:
        while True:
            message = await ws.receive_json()
            if isinstance(message, dict):
                await party.HUB.handle(room, member, message)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        await party.HUB.disconnect(room, member, ws)


@app.post("/api/exam/sessions/{session_id}/retreat")
def exam_retreat(session_id: str) -> dict[str, Any]:
    return exam.retreat(get_store(), session_id)


@app.get("/api/exam/sessions/{session_id}/results")
def exam_results(session_id: str) -> dict[str, Any]:
    return exam.results(get_store(), session_id)


class PreviewIn(BaseModel):
    text: str = Field(max_length=300)


class PreviewLines(BaseModel):
    lines: list[str] = Field(max_length=20)


@app.post("/api/math/preview-lines")
def math_preview_lines(body: PreviewLines) -> list[dict[str, Any]]:
    """Render each line of shown work as it was read (labels like "d =" kept as text)."""
    from .verification.steps import _latex, _segments

    out = []
    for line in body.lines:
        if not line.strip():
            out.append({"latex": None, "error": None})
            continue
        try:
            segs, _, label = _segments(line[:300], ("x", "y", "z", "t", "n", "k"))
            latex = _latex(segs)
            if label and latex:
                latex = r"\text{" + re.sub(r"[{}\\]", "", label) + "} = " + latex
            out.append({"latex": latex, "error": None})
        except UnsupportedExpression as err:
            out.append({"latex": None, "error": str(err)})
    return out


@app.post("/api/math/preview")
def math_preview(body: PreviewIn) -> dict[str, Any]:
    """Show the student how their typed answer was read, before they submit."""

    if not body.text.strip():
        return {"latex": None, "error": None}
    try:
        parts = [p for p in re.split(r",|\bor\b", body.text) if p.strip()]
        rendered = []
        for p in parts[:6]:
            p = re.sub(r"^\s*x\s*=", "", p)
            parse_math(p, DEFAULT_VARIABLES)  # must be valid, not just renderable
            rendered.append(to_latex(p, DEFAULT_VARIABLES))
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


class ResumeText(BaseModel):
    text: str = Field(min_length=1, max_length=60_000)


@app.post("/api/interview/resume/text")
def upload_resume_text(body: ResumeText) -> dict[str, Any]:
    return interview.upload_resume_text(get_store(), body.text)


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
