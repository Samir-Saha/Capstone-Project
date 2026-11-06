"""Turn uploaded course material into a verified boss.

Pipeline (runs as a background job):
  1. extract text from the PDF, page by page, into chunks
  2. ask the model for topics and computational question templates, each citing an
     exact quote from the material
  3. drop any template whose quote isn't actually in the source (grounding check)
  4. verify each template on 3 random instances with the math engine; keep only
     templates that pass every time
  5. create the course from the topics that kept at least one template

Material with nothing computable (an essay-only reading) produces no questions,
and the job says so. Conceptual question types are future work.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from pydantic import BaseModel, Field

from . import recall
from .content.courses import DECIMAL, EXACT, ROOTS, QuestionTemplate
from .ingest.pdf import Extraction
from .llm import LLMError, LLMProvider, generate_structured
from .store import Store, dumps, loads, new_id, now_iso
from .verification.math_engine import MathProblemSpec, MathTask, ParamSpec, TaskKind, verify_problem
from .verification.status import VerificationStatus

log = logging.getLogger("reps.generation")
PROMPT_VERSION = "course-gen-1"
MAX_SOURCE_CHARS = 24_000
VERIFY_SEEDS = (11, 22, 33)


class GenTemplate(BaseModel):
    prompt: str = Field(description="Question shown to the student; may contain {param} placeholders")
    kind: TaskKind
    expr: str = Field(description="Expression in x using + - * / ^ ( ), sin cos tan exp ln sqrt pi; may contain {param}")
    at: str | None = None
    lower: str | None = None
    upper: str | None = None
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    claimed_answer: str | None = None
    difficulty: int = Field(ge=1, le=3)
    hint: str = Field(max_length=300)
    method: str = Field(max_length=500)
    numeric_answer: bool = Field(description="True for word problems answered with a decimal number")
    source_chunk: int
    source_quote: str = Field(max_length=300, description="Exact text copied from that chunk that this question practices")


class GenTopic(BaseModel):
    name: str = Field(max_length=60)
    description: str = Field(max_length=200)
    templates: list[GenTemplate] = Field(max_length=4)


class GenCourse(BaseModel):
    boss_name: str = Field(max_length=40)
    topics: list[GenTopic] = Field(max_length=8)
    no_computational_content: bool = False


SYSTEM = (
    "You design practice questions for a study game from a student's course material. Only create questions "
    "whose answer can be computed: limits, derivatives, derivative at a point, definite or indefinite integrals, "
    "solving single-variable equations with finitely many real roots, or evaluating a numeric expression for a "
    "word problem. Each must practice something actually in the material, and source_quote must be copied exactly "
    "from the cited chunk. Use {param} placeholders with small integer ranges so every student gets fresh numbers. "
    "Use only x as the variable. If nothing in the material is computational, set no_computational_content to true "
    "and return no topics. Invent an original boss name that fits the subject."
)


def _friendly(err: Exception) -> str:
    text = str(err)
    if " 503" in text or " 429" in text or "high demand" in text:
        return "The AI service is overloaded right now. Wait a minute and click Build the boss again."
    if " 401" in text or " 403" in text or "API key" in text:
        return "The AI key was rejected. Check LLM_API_KEY in .env, then restart Reps."
    if " 404" in text:
        return "That AI model isn't available. Check LLM_MODEL in .env, then restart Reps."
    return "Question generation failed. Try again, or try fewer or smaller files."


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _spread(chunks: list, budget: int) -> list:
    """Chunks that fit the budget, sampled evenly across all the material rather than only the start."""
    if sum(len(c.text) for c in chunks) <= budget:
        return chunks
    avg = max(1, sum(len(c.text) for c in chunks) // len(chunks))
    k = max(1, budget // avg)
    step = len(chunks) / k
    picked = [chunks[min(len(chunks) - 1, int(i * step))] for i in range(k)]
    out, total = [], 0
    for c in picked:
        if total + len(c.text) > budget:
            break
        out.append(c)
        total += len(c.text)
    return out


def build_prompt(name: str, extraction: Extraction) -> str:
    parts, total = [], 0
    for c in _spread(extraction.chunks, MAX_SOURCE_CHARS):
        if total + len(c.text) > MAX_SOURCE_CHARS:
            break
        parts.append(f'<chunk index="{c.index}" pages="{c.page_start}-{c.page_end}">\n<untrusted>{c.text}</untrusted>\n</chunk>')
        total += len(c.text)
    return f"Course: {name}\n\n" + "\n\n".join(parts)


def to_template(g: GenTemplate, tid: str, topic_key: str) -> QuestionTemplate:
    return QuestionTemplate(
        id=tid,
        topic=topic_key,
        difficulty=g.difficulty,
        spec=MathProblemSpec(
            statement=g.prompt,
            params=g.params,
            task=MathTask(kind=g.kind, expr=g.expr, at=g.at, lower=g.lower, upper=g.upper),
            claimed_answer=g.claimed_answer,
        ),
        hint=g.hint,
        method=g.method,
        answer_format=DECIMAL if g.numeric_answer else (ROOTS if g.kind == "solve" else EXACT),
        rel_tol=0.01 if g.numeric_answer else None,
    )


def generate_course(store: Store, provider: LLMProvider | None, name: str, extraction: Extraction, job_id: str, document_id: str) -> dict[str, Any]:
    """Computational questions from the AI (when a key is set) plus recall questions built
    straight from the notes (always). Either alone is enough to make a boss."""

    def progress(**kw: Any) -> None:
        store.run("update jobs set progress = ? where id = ?", (dumps(kw), job_id))

    course_id = new_id()
    kept_topics: list[tuple[str, GenTopic, list[QuestionTemplate], list[dict]]] = []
    kept = rejected = 0
    boss = None
    ai_note = None
    if provider is not None:
        try:
            kept_topics, kept, rejected, boss = _ai_topics(store, provider, name, extraction, progress, course_id, document_id)
        except (LLMError, ValueError) as err:
            log.warning("AI generation failed, using questions from the notes only: %s", err)
            ai_note = _friendly(err)

    progress(stage="verifying", message="Building questions straight from your notes", kept=kept, rejected=rejected)
    recall_topics, recall_rejected = recall.build(course_id, extraction, f"{name}:{extraction.char_count}")
    for t in recall_topics:
        for rt in t["templates"]:
            store.run(
                "insert into verification_log (id, subject, subject_id, status, reason, method, created_at) values (?, 'generated_template', ?, 'verified', null, ?, ?)",
                (new_id(), rt.id, "grounded-recall", now_iso()),
            )
    # Skipped sentences aren't rejected questions (most sentences just aren't quizzable), so they aren't logged.
    n_recall = sum(len(t["templates"]) for t in recall_topics)
    if not kept_topics and not recall_topics:
        return {"course_id": None, "kept": 0, "rejected": rejected, "message": ai_note or "Not enough readable text to build questions from."}

    with store.tx() as db:
        db.execute(
            "insert into courses (id, name, code, boss_name, kind, created_at) values (?, ?, null, ?, 'uploaded', ?)",
            (course_id, name, boss or recall.boss_name(name, recall_topics), now_iso()),
        )
        pos = 0
        for topic_key, topic, templates, sources in kept_topics:
            tid = f"{course_id}:{topic_key}"
            db.execute("insert into topics (id, course_id, name, description, position) values (?, ?, ?, ?, ?)", (tid, course_id, topic.name, topic.description, pos))
            pos += 1
            for tpl, src in zip(templates, sources, strict=False):
                db.execute(
                    "insert into templates (id, course_id, topic_id, difficulty, body, source) values (?, ?, ?, ?, ?, ?)",
                    (tpl.id, course_id, tid, tpl.difficulty, tpl.model_dump_json(), dumps(src)),
                )
        for t in recall_topics:
            tid = f"{course_id}:{t['key']}"
            db.execute("insert into topics (id, course_id, name, description, position) values (?, ?, ?, ?, ?)", (tid, course_id, t["name"], t["description"], pos))
            pos += 1
            for rt in t["templates"]:
                db.execute(
                    "insert into templates (id, course_id, topic_id, difficulty, body, source) values (?, ?, ?, ?, ?, ?)",
                    (rt.id, course_id, tid, rt.difficulty, rt.model_dump_json(), dumps({"document_id": document_id, "pages": rt.pages, "quote": rt.quote})),
                )
        db.execute("update documents set course_id = ?, status = 'ready' where id = ?", (course_id, document_id))
    parts = []
    if kept:
        parts.append(f"{kept} computational question types verified by SymPy ({rejected} rejected)")
    parts.append(f"{n_recall} questions built straight from your notes")
    if ai_note:
        parts.append(f"AI questions skipped: {ai_note}")
    elif provider is None:
        parts.append("Add an AI key to also get computational problems")
    return {
        "course_id": course_id,
        "kept": kept + n_recall,
        "rejected": rejected,
        "ai_kept": kept,
        "ai_rejected": rejected,
        "from_notes": n_recall,
        "message": ". ".join(parts) + ".",
    }


def _ai_topics(store: Store, provider: LLMProvider, name: str, extraction: Extraction, progress, course_id: str, document_id: str):
    progress(stage="generating", message="Reading your material and drafting questions")
    plan = generate_structured(provider, SYSTEM, build_prompt(name, extraction), GenCourse, PROMPT_VERSION, max_tokens=6000)
    if plan.no_computational_content or not plan.topics:
        return [], 0, 0, None

    chunks = {c.index: c for c in extraction.chunks}
    kept_topics: list[tuple[str, GenTopic, list[QuestionTemplate], list[dict]]] = []
    kept = rejected = 0
    total = sum(len(t.templates) for t in plan.topics)
    done = 0
    for ti, topic in enumerate(plan.topics):
        topic_key = f"t{ti}"
        good: list[QuestionTemplate] = []
        sources: list[dict] = []
        for gi, g in enumerate(topic.templates):
            done += 1
            progress(stage="verifying", message=f"Verifying question {done} of {total}", kept=kept, rejected=rejected)
            chunk = chunks.get(g.source_chunk)
            reason = None
            if chunk is None or _norm(g.source_quote) not in _norm(chunk.text):
                reason = "source quote not found in the material"
            else:
                try:
                    tpl = to_template(g, f"{course_id}:{topic_key}:{gi}", topic_key)
                except ValueError as err:
                    tpl, reason = None, f"invalid template: {err}"
                if tpl is not None:
                    for seed in VERIFY_SEEDS:
                        result = verify_problem(tpl.spec, seed)
                        if result.status is not VerificationStatus.VERIFIED:
                            reason = result.reason or result.status.value
                            break
            store.run(
                "insert into verification_log (id, subject, subject_id, status, reason, method, created_at) values (?, 'generated_template', ?, ?, ?, ?, ?)",
                (new_id(), f"{course_id}:{topic_key}:{gi}", "rejected" if reason else "verified", reason, "grounding+symbolic+numeric", now_iso()),
            )
            if reason:
                rejected += 1
                continue
            kept += 1
            good.append(tpl)
            sources.append({"document_id": document_id, "pages": [chunk.page_start, chunk.page_end], "quote": g.source_quote})
        if good:
            kept_topics.append((topic_key, topic, good, sources))

    return kept_topics, kept, rejected, plan.boss_name


def start_job(store: Store, provider: LLMProvider | None, name: str, filename: str, extraction: Extraction) -> dict[str, Any]:
    job_id, doc_id = new_id(), new_id()
    store.run(
        "insert into documents (id, filename, page_count, char_count, status, created_at) values (?, ?, ?, ?, 'processing', ?)",
        (doc_id, filename, extraction.page_count, extraction.char_count, now_iso()),
    )
    store.run(
        "insert into jobs (id, kind, status, progress, created_at) values (?, 'generate_course', 'queued', ?, ?)",
        (job_id, dumps({"stage": "queued", "message": "Waiting to start"}), now_iso()),
    )

    def work() -> None:
        store.run("update jobs set status = 'running' where id = ?", (job_id,))
        try:
            result = generate_course(store, provider, name, extraction, job_id, doc_id)
            status = "succeeded" if result["course_id"] else "failed"
            store.run(
                "update jobs set status = ?, result = ?, error = ?, finished_at = ? where id = ?",
                (status, dumps(result), None if result["course_id"] else result["message"], now_iso(), job_id),
            )
            if not result["course_id"]:
                store.run("update documents set status = 'failed', error = ? where id = ?", (result["message"], doc_id))
        except (LLMError, ValueError) as err:
            log.warning("generation job %s failed: %s", job_id, err)
            store.run(
                "update jobs set status = 'failed', error = ?, finished_at = ? where id = ?",
                (_friendly(err), now_iso(), job_id),
            )
            store.run("update documents set status = 'failed', error = ? where id = ?", (str(err)[:300], doc_id))

    threading.Thread(target=work, name=f"job-{job_id[:8]}", daemon=True).start()
    return job_view(store, job_id)


def job_view(store: Store, job_id: str) -> dict[str, Any] | None:
    j = store.one("select * from jobs where id = ?", (job_id,))
    if not j:
        return None
    return {
        "id": j["id"],
        "kind": j["kind"],
        "status": j["status"],
        "progress": loads(j["progress"]),
        "result": loads(j["result"]),
        "error": j["error"],
    }
