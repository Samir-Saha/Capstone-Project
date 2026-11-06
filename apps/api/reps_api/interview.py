"""Interview Mode: the Gauntlet.

What is measured vs judged
  measured   delivery metrics: speaking time, pace, pauses (from microphone audio
             levels recorded in the browser), filler words and text checks (counted
             from the transcript), code verdicts (run against tests).
  judged     STAR scores and written feedback, only when an AI model is configured,
             and always labeled as AI evaluation.

Follow-up questions come from transparent rules (no number in a resume answer ->
"how did you measure that?"), so the interviewer adapts even without a model.
"""

from __future__ import annotations

import logging
import random
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import arena
from .ingest.pdf import ExtractionError, extract_pdf
from .llm import LLMError, LLMProvider, generate_structured, llm_from_env
from .progression import XP_RULES, award
from .store import Store, dumps, loads, new_id, now_iso

log = logging.getLogger("reps.interview")

Role = Literal["software", "quant", "ai_ml", "general"]
Kind = Literal["behavioral", "technical", "mixed", "intro"]

ROLE_LABELS = {
    "software": "Software engineering",
    "quant": "Quant and trading",
    "ai_ml": "AI and machine learning",
    "general": "General internship",
}

BEHAVIORAL = [
    "Tell me about a time you had to learn something new quickly to get a project done.",
    "Describe a time you disagreed with a teammate. How did you handle it?",
    "Tell me about a project that didn't go as planned. What did you do?",
    "Walk me through the project you're proudest of. What part was yours?",
    "Tell me about a time you led a group without being officially in charge.",
    "Describe a mistake you made that affected other people. What happened next?",
]

ROLE_QUESTIONS = {
    "software": ["Tell me about the hardest bug you've tracked down. How did you find it?"],
    "quant": ["Tell me about a time you made a decision with incomplete information. How did you weigh the risk?"],
    "ai_ml": ["Tell me about a time a model or experiment gave you results you didn't expect. What did you do?"],
    "general": ["Why this kind of role, and what have you done that shows you'd be good at it?"],
}

TECH_WORDS = [
    "python",
    "java",
    "c++",
    "c#",
    "javascript",
    "typescript",
    "react",
    "next.js",
    "node",
    "fastapi",
    "flask",
    "django",
    "sql",
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "git",
    "linux",
    "pytorch",
    "tensorflow",
    "scikit-learn",
    "pandas",
    "numpy",
    "langchain",
    "openai",
    "llm",
    "rag",
    "supabase",
    "firebase",
    "graphql",
    "rest",
    "spark",
    "tableau",
    "excel",
    "r",
    "matlab",
    "go",
    "rust",
    "swift",
    "kotlin",
]

ACTION_VERBS = re.compile(
    r"^(built|led|created|designed|developed|implemented|launched|reduced|increased|improved|managed|organized|"
    r"automated|optimized|cut|grew|won|founded|taught|trained|deployed|shipped|analyzed|scaled|raised|mentored|coordinated)\b",
    re.I,
)
NUMBERISH = re.compile(r"\d|percent|\bhalf\b|\bdouble[d]?\b|\btriple[d]?\b|\bthousand|\bhundred|\bmillion", re.I)
# Bullets as they come out of real PDFs: glyphs, dashes, icon-font private-use
# characters, and "?" where the PDF's bullet glyph has no Unicode mapping.
BULLET = re.compile(r"^\s*[•\-–▪●◦‣*·?-]\s+|^\s*o\s+(?=[A-Z])")


class ResumeClaim(BaseModel):
    text: str
    measurable: bool
    technologies: list[str] = Field(default_factory=list)


class InterviewError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# ------------------------------------------------------------------ resume


def _technologies(text: str) -> list[str]:
    low = text.lower()
    found = []
    for word in TECH_WORDS:
        pattern = rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])"
        if word == "r":
            pattern = r"(?<![a-z0-9])R(?![a-zA-Z0-9])"
            if re.search(pattern, text):
                found.append("R")
            continue
        if re.search(pattern, low):
            found.append(word)
    return found


def extract_claims(text: str) -> list[ResumeClaim]:
    """Rule-based: bullet lines (or lines starting with an action verb), joined
    across PDF line wraps. Measurable = mentions a number or quantity."""
    lines = [line.rstrip() for line in text.splitlines()]
    items: list[str] = []
    current: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                items.append(current)
            current = None
            continue
        if BULLET.match(line) or ACTION_VERBS.match(stripped):
            if current:
                items.append(current)
            current = BULLET.sub("", line).strip()
        elif current is not None and (stripped[:1].islower() or len(current) < 60):
            current += " " + stripped
        else:
            if current:
                items.append(current)
            current = None
    if current:
        items.append(current)

    claims = []
    seen = set()
    for item in items:
        item = re.sub(r"\s+", " ", item).strip()
        if len(item) < 25 or item.lower() in seen:
            continue
        seen.add(item.lower())
        claims.append(ResumeClaim(text=item[:300], measurable=bool(NUMBERISH.search(item)), technologies=_technologies(item)))
    return claims


def upload_resume(store: Store, filename: str, data: bytes) -> dict[str, Any]:
    try:
        extraction = extract_pdf(data)
    except ExtractionError as err:
        raise InterviewError(422, str(err)) from err
    return _save_resume(store, filename, "\n\n".join(p.text for p in extraction.pages))


def upload_resume_text(store: Store, text: str) -> dict[str, Any]:
    text = text.replace("\r\n", "\n").strip()[:60_000]
    if len(text) < 80:
        raise InterviewError(422, "Paste your whole resume, not just a line or two.")
    return _save_resume(store, "Pasted resume", text)


def _save_resume(store: Store, filename: str, text: str) -> dict[str, Any]:
    claims = extract_claims(text)
    rid = new_id()
    store.run(
        "insert into resumes (id, filename, text, claims, extraction, created_at) values (?, ?, ?, ?, 'rule-based', ?)",
        (rid, re.sub(r"[^\w.\- ]", "_", filename)[:120], text, dumps([c.model_dump() for c in claims]), now_iso()),
    )
    return resume_view(store, rid)


def resume_view(store: Store, resume_id: str) -> dict[str, Any]:
    r = store.one("select id, filename, claims, extraction, created_at from resumes where id = ?", (resume_id,))
    if not r:
        raise InterviewError(404, "Resume not found.")
    claims = loads(r["claims"])
    return {
        "id": r["id"],
        "filename": r["filename"],
        "extraction": r["extraction"],
        "claims": claims,
        "technologies": sorted({t for c in claims for t in c["technologies"]}),
        "created_at": r["created_at"],
    }


def latest_resume(store: Store) -> dict[str, Any] | None:
    r = store.one("select id from resumes order by created_at desc limit 1")
    return resume_view(store, r["id"]) if r else None


# ------------------------------------------------------------------ sessions


class StartInterview(BaseModel):
    role: Role = "software"
    kind: Kind = "behavioral"
    length: int = Field(default=4, ge=2, le=6)
    resume_id: str | None = None


INTRO_QUESTION = "Tell me about yourself."


def _plan(req: StartInterview, claims: list[dict[str, Any]], rng: random.Random, store: Store) -> list[dict[str, Any]]:
    if req.kind == "intro":
        return [{"kind": "intro", "text": INTRO_QUESTION, "tip": "Aim for 60 to 90 seconds: who you are now, what you've done, and why this role."}]
    plan: list[dict[str, Any]] = []
    n = req.length
    technical = 1 if req.kind == "mixed" else (n if req.kind == "technical" else 0)
    technical = min(technical, 2)
    if req.kind == "technical":
        n = technical
    behavioral_slots = n - technical

    measurable = [c for c in claims if c["measurable"]]
    other = [c for c in claims if not c["measurable"]]
    claim_pool = measurable[:4] + other[:2]
    resume_slots = min(len(claim_pool), behavioral_slots // 2 + (1 if behavioral_slots % 2 else 0)) if claim_pool else 0
    for claim in claim_pool[:resume_slots]:
        plan.append(
            {
                "kind": "resume",
                "text": f"Your resume says: “{claim['text']}” Walk me through what you did there and how you know it worked.",
                "claim": claim["text"],
            }
        )
    bank = ROLE_QUESTIONS[req.role] + rng.sample(BEHAVIORAL, k=len(BEHAVIORAL))
    for q in bank[: behavioral_slots - resume_slots]:
        plan.append({"kind": "behavioral", "text": q})
    rng.shuffle(plan)

    if technical:
        problems = [p for p in arena.list_problems(store) if p["difficulty"] == "easy"] or arena.list_problems(store)
        for p in rng.sample(problems, k=min(technical, len(problems))):
            plan.append(
                {
                    "kind": "technical",
                    "text": f"Let's do a coding question: {p['title']}. Talk me through your approach, then write a solution.",
                    "slug": p["slug"],
                }
            )
    return plan


def start(store: Store, req: StartInterview, rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.Random()
    claims: list[dict[str, Any]] = []
    if req.resume_id:
        claims = resume_view(store, req.resume_id)["claims"]
    plan = _plan(req, claims, rng, store)
    sid = new_id()
    store.run(
        "insert into interview_sessions (id, role, kind, resume_id, plan, status, started_at) values (?, ?, ?, ?, ?, 'active', ?)",
        (sid, req.role, req.kind, req.resume_id, dumps(plan), now_iso()),
    )
    return state(store, sid)


def _session(store: Store, session_id: str) -> dict[str, Any]:
    s = store.one("select * from interview_sessions where id = ?", (session_id,))
    if not s:
        raise InterviewError(404, "Interview not found.")
    return s


def state(store: Store, session_id: str) -> dict[str, Any]:
    s = _session(store, session_id)
    plan = loads(s["plan"])
    turns = store.all("select idx from interview_turns where session_id = ? order by idx", (session_id,))
    current = len(turns)
    question = None
    if current < len(plan) and s["status"] == "active":
        item = plan[current]
        question = {"index": current, **item}
        if item["kind"] == "technical":
            question["problem"] = arena.problem_detail(store, item["slug"])
    return {
        "id": s["id"],
        "role": s["role"],
        "role_label": ROLE_LABELS[s["role"]],
        "kind": s["kind"],
        "status": s["status"],
        "total": len(plan),
        "answered": current,
        "question": question,
        "ai_feedback_available": llm_from_env() is not None,
    }


# ------------------------------------------------------------------ measurement


class AudioMetrics(BaseModel):
    """Raw measurements from the browser's audio analyser (Web Audio API)."""

    duration_s: float = Field(ge=0, le=1800)
    speaking_s: float = Field(ge=0, le=1800)
    pauses_ms: list[int] = Field(default_factory=list, max_length=2000)


class AnswerIn(BaseModel):
    index: int = Field(ge=0)
    transcript: str = Field(max_length=20_000)
    input_mode: Literal["voice", "text"]
    audio: AudioMetrics | None = None
    code: str | None = Field(default=None, max_length=50_000)


FILLERS = ["um", "uh", "erm", "er", "uhm", "hmm", "you know", "i mean", "kind of", "sort of", "basically", "literally", "like,"]
PAUSE_MS = 600
LONG_PAUSE_MS = 2000


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9'%$.]+", text)


def filler_counts(text: str) -> dict[str, int]:
    low = " " + re.sub(r"\s+", " ", text.lower()) + " "
    counts = {}
    for f in FILLERS:
        if f == "like,":
            n = len(re.findall(r"(?:^|[ ,]) ?like,", low))
        else:
            n = len(re.findall(rf"(?<![a-z']){re.escape(f)}(?![a-z'])", low))
        if n:
            counts[f.rstrip(",")] = n
    return counts


def measure(answer: AnswerIn) -> dict[str, Any]:
    words = _words(answer.transcript)
    fillers = filler_counts(answer.transcript)
    filler_total = sum(fillers.values())
    out: dict[str, Any] = {
        "words": len(words),
        "fillers": fillers,
        "filler_total": filler_total,
        "source": "typed answer: delivery not measured" if answer.input_mode == "text" else "microphone audio levels + speech transcript",
    }
    if answer.input_mode == "voice" and answer.audio:
        a = answer.audio
        pauses = [p for p in a.pauses_ms if p >= PAUSE_MS]
        minutes = a.speaking_s / 60
        out.update(
            {
                "duration_s": round(a.duration_s, 1),
                "speaking_s": round(a.speaking_s, 1),
                "wpm": round(len(words) / minutes) if a.speaking_s >= 5 else None,
                "pause_count": len(pauses),
                "long_pauses": sum(1 for p in pauses if p >= LONG_PAUSE_MS),
                "longest_pause_s": round(max(pauses) / 1000, 1) if pauses else 0,
                "fillers_per_min": round(filler_total / (a.duration_s / 60), 1) if a.duration_s >= 10 else None,
            }
        )
    return out


RESULT_WORDS = re.compile(
    r"\b(result|resulted|outcome|so that|which meant|ended up|led to|increased|decreased|reduced|improved|cut|grew|saved|won|shipped|launched)\b",
    re.I,
)
MEASURE_WORDS = re.compile(r"\b(measured|tracked|metric|baseline|benchmark|compared|a/b|before and after|survey|logged|dashboard)\b", re.I)


def checks(answer: AnswerIn, kind: str) -> dict[str, Any]:
    text = answer.transcript
    i_count = len(re.findall(r"\b(i|i'm|i've|i'd|me|my)\b", text, re.I))
    we_count = len(re.findall(r"\b(we|we're|we've|us|our)\b", text, re.I))
    words = len(_words(text))
    out = {
        "length": {"words": words, "ok": 90 <= words <= 400 if kind != "technical" else words >= 30},
        "mentions_number": bool(NUMBERISH.search(text)),
        "result_language": bool(RESULT_WORDS.search(text)),
        "ownership": {"i": i_count, "we": we_count, "ok": i_count >= we_count or we_count < 3},
    }
    if kind == "resume":
        out["explains_measurement"] = bool(MEASURE_WORDS.search(text)) or bool(NUMBERISH.search(text))
    return out


# ------------------------------------------------------------------ "tell me about yourself"

PRESENT_RE = re.compile(r"\b(i'?m|i am|currently|right now|these days|studying|majoring|a (junior|senior|sophomore|freshman)|student at)\b", re.I)
PAST_RE = re.compile(
    r"\b(previously|before that|last (summer|year|semester)|interned|internship|worked|built|led|founded|started|created|developed|shipped|launched|managed|taught)\b",
    re.I,
)
FUTURE_RE = re.compile(
    r"\b(looking (for|to)|excited|want to|hoping to|next|this role|this position|your team|the team here|goal|i'?d love|interested in|that'?s why)\b", re.I
)


NAME_STOP = {
    "experience",
    "education",
    "skills",
    "projects",
    "project",
    "summary",
    "objective",
    "technical",
    "relevant",
    "coursework",
    "languages",
    "tools",
    "frameworks",
    "leadership",
    "activities",
    "awards",
    "honors",
    "certifications",
    "interests",
    "work",
    "the",
    "and",
    "for",
    "with",
    "inc",
    "llc",
    "present",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "gpa",
    "email",
    "phone",
    "linkedin",
    "github",
    "remote",
    "bachelor",
    "bs",
    "ba",
    "university",
    "college",
    "school",
    "new",
    "york",
    "jersey",
    "nj",
    "ny",
    "usa",
    "intern",
    "internship",
    "assistant",
    "manager",
    "developer",
    "engineer",
    "software",
    "data",
    "science",
    "computer",
    "student",
    "member",
    "lead",
}
CONTENT_STOP = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "that",
    "this",
    "over",
    "across",
    "while",
    "using",
    "by",
    "of",
    "to",
    "in",
    "on",
    "a",
    "an",
    "at",
    "as",
    "per",
    "via",
    "their",
    "them",
    "its",
    "our",
    "your",
    "weekly",
    "daily",
    "new",
    "all",
    "more",
    "than",
}
SPOKEN = [(r"\bc\s*plus\s*plus\b", "c++"), (r"\bc\s*sharp\b", "c#"), (r"\bnext\s*js\b", "next.js"), (r"\bnode\s*js\b", "node")]


def resume_terms(text: str) -> list[str]:
    """Names worth saying out loud: tools from anywhere on the resume (skills section too), proper names
    such as companies, schools and projects, and two-word phrases from the bullets ("order book")."""
    terms: list[str] = list(_technologies(text))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    for line in lines[1:]:  # the first line is the candidate's own name
        body = BULLET.sub("", line).strip()
        for m in re.finditer(r"\b[A-Z][A-Za-z0-9&+]*(?:\s+[A-Z][A-Za-z0-9&+]*)*", body):
            words = [w for w in m.group(0).split() if w.lower() not in NAME_STOP and not ACTION_VERBS.match(w.lower())]
            phrase = " ".join(words)
            if len(phrase) >= 3 and not phrase.isdigit():
                terms.append(phrase)
        words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z+#-]{2,}", body)]
        for a, b in zip(words, words[1:], strict=False):
            if not ({a, b} & (CONTENT_STOP | NAME_STOP)) and not ACTION_VERBS.match(a):
                terms.append(f"{a} {b}")
    seen: set[str] = set()
    return [t for t in terms if not (t.lower() in seen or seen.add(t.lower()))]


def resume_hits(answer: str, terms: list[str]) -> list[str]:
    low = answer.lower()
    for pattern, repl in SPOKEN:
        low = re.sub(pattern, repl, low)
    hits = [t for t in terms if re.search(rf"(?<![a-z0-9]){re.escape(t.lower())}(?![a-z0-9])", low)]
    # Prefer proper names and tools over generic two-word phrases in the feedback.
    return sorted(hits, key=lambda t: (t.islower() and " " in t, -len(t)))


REPEAT_RE = re.compile(r"\b([A-Za-z']+)(?:[\s,.]+\1\b)+", re.I)


def _fluency(text: str, metrics: dict[str, Any]) -> tuple[bool, str]:
    """Delivery from what can be measured. Browser speech recognition drops most "um"s, so pauses
    and repeated words (stutters like "and and") from the transcript and mic carry most of the signal."""
    words = max(1, len(_words(text)))
    problems: list[str] = []
    fillers = metrics.get("filler_total", 0)
    fpm = metrics.get("fillers_per_min")
    if (fpm is not None and fpm > 4) or (fpm is None and fillers > 3):
        problems.append(f"{fillers} filler words")
    spoken = text
    for pattern, repl in SPOKEN:
        spoken = re.sub(pattern, repl, spoken, flags=re.I)
    repeats = [m.group(0) for m in REPEAT_RE.finditer(spoken) if m.group(1).lower() not in ("had", "that", "very", "so", "bye")]
    if repeats:
        problems.append(f"{len(repeats)} stutter{'s' if len(repeats) != 1 else ''} (" + ", ".join(f"“{r}”" for r in repeats[:3]) + ")")
    ands = len(re.findall(r"\band\b", text, re.I))
    if words >= 25 and ands / words > 0.07:
        problems.append(f"“and” {ands} times; end some sentences instead")
    duration = metrics.get("duration_s")
    if duration:
        long_pauses = metrics.get("long_pauses", 0)
        pauses = metrics.get("pause_count", 0)
        per_min = pauses / (duration / 60) if duration >= 5 else 0
        speaking = metrics.get("speaking_s") or 0
        if long_pauses:
            problems.append(f"{long_pauses} pause{'s' if long_pauses != 1 else ''} over 2 seconds")
        elif per_min > 12:
            problems.append(f"{pauses} hesitations in {round(duration)} seconds")
        if duration >= 8 and speaking / duration < 0.6:
            problems.append(f"speaking only {round(100 * speaking / duration)}% of the time")
    pace = f", {metrics['wpm']} words per minute" if metrics.get("wpm") else ""
    if problems:
        joined = "; ".join(problems)
        return False, joined[:1].upper() + joined[1:] + pace
    return True, "No stalls, stutters or filler words caught" + pace


def grade_intro(text: str, metrics: dict[str, Any], resume_terms: list[str]) -> dict[str, Any]:
    """Rubric for a pitch: present, past, future, proof, tie to the resume, length, delivery. Every item is a check on what was said."""
    words = len(_words(text))
    duration = metrics.get("duration_s")
    voiced = duration is not None
    if voiced:
        length_ok = 45 <= duration <= 120
        length_detail = f"{round(duration)} seconds" + ("" if length_ok else (", aim for 60 to 90" if duration < 45 else ", trim to under 2 minutes"))
    else:
        length_ok = 110 <= words <= 300
        length_detail = f"{words} words" + ("" if length_ok else (", aim for about 150 to 250" if words < 110 else ", trim it to under 300"))
    delivery_ok, delivery_detail = _fluency(text, metrics)
    hits = resume_hits(text, resume_terms)
    items = [
        {
            "key": "present",
            "label": "Present: who you are now",
            "points": 15,
            "ok": bool(PRESENT_RE.search(text)),
            "detail": "Open with where you are today: school, year, major or current role.",
        },
        {
            "key": "past",
            "label": "Past: what you've done",
            "points": 15,
            "ok": bool(PAST_RE.search(text)),
            "detail": "Name one or two things you built, led or worked on.",
        },
        {
            "key": "future",
            "label": "Future: why this role",
            "points": 20,
            "ok": bool(FUTURE_RE.search(text)),
            "detail": "Close with what you want next and why it's this team.",
        },
        {
            "key": "proof",
            "label": "Proof: a specific number",
            "points": 15,
            "ok": bool(NUMBERISH.search(text)),
            "detail": "One number makes it real: users, percent faster, people led.",
        },
        {
            "key": "resume",
            "label": "Ties to your resume",
            "points": 10,
            "ok": bool(hits) if resume_terms else None,
            "detail": (f"Mentioned {', '.join(hits[:4])}" if hits else "Mention something from your resume by name.")
            if resume_terms
            else "Attach a resume to check this.",
        },
        {"key": "length", "label": "Length", "points": 10, "ok": length_ok, "detail": length_detail},
        {"key": "delivery", "label": "Delivery: smooth, no stalls", "points": 15, "ok": delivery_ok, "detail": delivery_detail},
    ]
    scored = [i for i in items if i["ok"] is not None]
    possible = sum(i["points"] for i in scored)
    earned = sum(i["points"] for i in scored if i["ok"])
    score = round(100 * earned / possible) if possible else 0
    order = [i for i in ("present", "past", "future") if next(x for x in items if x["key"] == i)["ok"]]
    return {
        "score": score,
        "grade": "Strong" if score >= 85 else "Solid" if score >= 65 else "Needs work",
        "items": items,
        "structure": " → ".join(order) if order else "none found",
        "next_step": next((i["detail"] for i in items if i["ok"] is False), "Record it once more and keep it this tight."),
    }


def follow_up(item: dict[str, Any], chk: dict[str, Any]) -> str | None:
    if item["kind"] == "resume" and not chk.get("explains_measurement"):
        return "How did you measure that result? What was the number before, and what was it after?"
    if item["kind"] in ("behavioral", "resume") and not chk["ownership"]["ok"]:
        return f"You said “we” {chk['ownership']['we']} times. What part of that was specifically yours?"
    if item["kind"] == "behavioral" and not (chk["result_language"] or chk["mentions_number"]):
        return "How did it turn out? What changed because of what you did?"
    return None


def submit(store: Store, session_id: str, answer: AnswerIn) -> dict[str, Any]:
    s = _session(store, session_id)
    if s["status"] != "active":
        raise InterviewError(409, "This interview is finished.")
    plan = loads(s["plan"])
    done = store.one("select count(*) n from interview_turns where session_id = ?", (session_id,))["n"]
    if answer.index != done:
        existing = store.one("select * from interview_turns where session_id = ? and idx = ?", (session_id, answer.index))
        if existing:  # retried request
            return {"turn": _turn_view(existing), "session": state(store, session_id), "xp": 0}
        raise InterviewError(409, "That isn't the current question.")
    if not answer.transcript.strip() and not answer.code:
        raise InterviewError(422, "Say or type an answer first.")
    item = plan[answer.index]

    metrics = measure(answer)
    chk = checks(answer, item["kind"])
    if item["kind"] == "intro":
        terms: list[str] = []
        if s["resume_id"]:
            row = store.one("select text from resumes where id = ?", (s["resume_id"],))
            terms = resume_terms(row["text"] if row else "")
        chk["intro"] = grade_intro(answer.transcript, metrics, terms)
    if item["kind"] == "technical":
        if answer.code:
            result = arena.grade(store, item["slug"], answer.code, "python", submit=True)
            chk["code"] = {k: result[k] for k in ("verdict", "passed", "total", "hidden_passed", "hidden_total", "error")}
        else:
            chk["code"] = {"verdict": "not_submitted"}

    # Adaptive follow-up: at most one per original question, two per interview.
    already = sum(1 for p in plan if p["kind"] == "follow_up")
    fu = follow_up(item, chk) if item["kind"] not in ("follow_up", "intro") and already < 2 else None
    if fu:
        plan.insert(answer.index + 1, {"kind": "follow_up", "text": fu, "parent": answer.index})

    turn_id = new_id()
    with store.tx() as db:
        db.execute(
            "insert into interview_turns (id, session_id, idx, question, question_source, answer, input_mode, metrics, checks, created_at) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (turn_id, session_id, answer.index, item["text"], item["kind"], answer.transcript, answer.input_mode, dumps(metrics), dumps(chk), now_iso()),
        )
        db.execute("update interview_sessions set plan = ? where id = ?", (dumps(plan), session_id))
    xp = award(store, "interview_answer", XP_RULES["interview_answer"], "interview_turn", turn_id)
    turn = store.one("select * from interview_turns where id = ?", (turn_id,))
    return {"turn": _turn_view(turn), "follow_up_added": fu, "session": state(store, session_id), "xp": xp}


# ------------------------------------------------------------------ AI evaluation


class StarScore(BaseModel):
    index: int
    situation: int = Field(ge=0, le=4)
    task: int = Field(ge=0, le=4)
    action: int = Field(ge=0, le=4)
    result: int = Field(ge=0, le=4)
    specificity: int = Field(ge=0, le=4)
    strengths: list[str] = Field(max_length=3)
    missing: list[str] = Field(max_length=3)
    improvement: str = Field(max_length=400)
    quote: str = Field(max_length=300, description="An exact excerpt from the answer that supports the scores")


class StarReport(BaseModel):
    answers: list[StarScore]


STAR_SYSTEM = (
    "You are an interview coach scoring practice answers with the STAR rubric. Score each of situation, task, "
    "action and result from 0 (missing) to 4 (clear and specific), plus specificity from 0 to 4. Judge only what "
    "the candidate actually said. Never assume a resume claim is true or false; note when evidence is missing. "
    "The quote must be copied exactly from that answer."
)
STAR_PROMPT_VERSION = "star-eval-1"


def ai_star(provider: LLMProvider, turns: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    scored = [t for t in turns if t["question_source"] not in ("technical", "intro")]
    if not scored:
        return {}
    body = "\n\n".join(f'<answer index="{t["idx"]}">\nQuestion: {t["question"]}\n<untrusted>{t["answer"]}</untrusted>\n</answer>' for t in scored)
    report = generate_structured(provider, STAR_SYSTEM, body, StarReport, STAR_PROMPT_VERSION, max_tokens=3000)
    by_index = {t["idx"]: t for t in scored}
    out = {}
    for s in report.answers:
        if s.index not in by_index:
            continue
        data = s.model_dump()
        if s.quote and s.quote not in by_index[s.index]["answer"]:
            data["quote"] = None  # not an exact excerpt: drop rather than show a made-up quote
        out[s.index] = data
    return out


def finish(store: Store, session_id: str, provider: LLMProvider | None = None) -> dict[str, Any]:
    s = _session(store, session_id)
    xp = 0
    if s["status"] == "active":
        turns = store.all("select * from interview_turns where session_id = ? order by idx", (session_id,))
        if not turns:
            raise InterviewError(409, "Answer at least one question before finishing.")
        provider = provider if provider is not None else llm_from_env()
        ai_error = None
        if provider is not None:
            try:
                scores = ai_star(provider, turns)
                for idx, data in scores.items():
                    store.run("update interview_turns set ai_feedback = ? where session_id = ? and idx = ?", (dumps(data), session_id, idx))
            except (LLMError, ValueError) as err:
                log.warning("AI evaluation failed: %s", err)
                ai_error = "AI scoring failed this time. Your measured results are still below."
        store.run("update interview_sessions set status = 'completed', completed_at = ? where id = ?", (now_iso(), session_id))
        xp = award(store, "interview_finished", XP_RULES["interview_finished"], "interview_session", session_id)
        rep = report(store, session_id)
        rep["ai_error"] = ai_error
        rep["xp"] = xp
        return rep
    return report(store, session_id)


def _turn_view(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": t["idx"],
        "question": t["question"],
        "source": t["question_source"],
        "answer": t["answer"],
        "input_mode": t["input_mode"],
        "metrics": loads(t["metrics"]),
        "checks": loads(t["checks"]),
        "ai_feedback": loads(t["ai_feedback"]),
    }


def report(store: Store, session_id: str) -> dict[str, Any]:
    s = _session(store, session_id)
    turns = [_turn_view(t) for t in store.all("select * from interview_turns where session_id = ? order by idx", (session_id,))]
    voiced = [t["metrics"] for t in turns if t["metrics"].get("speaking_s")]
    speaking = sum(m["speaking_s"] for m in voiced)
    words = sum(m["words"] for m in voiced)
    duration = sum(m["duration_s"] for m in voiced)
    fillers = sum(m["filler_total"] for m in voiced)
    summary = {
        "answers": len(turns),
        "voice_answers": len(voiced),
        "avg_wpm": round(words / (speaking / 60)) if speaking >= 5 else None,
        "fillers_per_min": round(fillers / (duration / 60), 1) if duration >= 10 else None,
        "pauses": sum(m.get("pause_count", 0) for m in voiced),
        "long_pauses": sum(m.get("long_pauses", 0) for m in voiced),
        "speaking_s": round(speaking, 1),
        "with_numbers": sum(1 for t in turns if t["checks"].get("mentions_number")),
        "owned": sum(1 for t in turns if t["checks"]["ownership"]["ok"]),
    }
    ai_scored = any(t["ai_feedback"] for t in turns)
    focus = []
    if summary["answers"] and summary["with_numbers"] < summary["answers"] / 2:
        focus.append("Put a number in your results: how much, how many, how fast.")
    if summary["owned"] < summary["answers"]:
        focus.append("Say what you did. Swap some “we” for “I” where it was your work.")
    if summary["avg_wpm"] and summary["avg_wpm"] > 175:
        focus.append(f"Slow down a little: {summary['avg_wpm']} words per minute is fast for an interview.")
    if summary["avg_wpm"] and summary["avg_wpm"] < 110:
        focus.append(f"Pick up the pace: {summary['avg_wpm']} words per minute can sound hesitant.")
    if summary["long_pauses"] >= 3:
        focus.append("Several pauses ran over 2 seconds. A quick plan before answering helps.")
    return {
        "id": s["id"],
        "role_label": ROLE_LABELS[s["role"]],
        "kind": s["kind"],
        "status": s["status"],
        "started_at": s["started_at"],
        "completed_at": s["completed_at"],
        "turns": turns,
        "summary": summary,
        "ai_scored": ai_scored,
        "ai_available": llm_from_env() is not None,
        "focus": focus,
        "intro": next((t["checks"]["intro"] for t in turns if t["checks"].get("intro")), None),
    }
