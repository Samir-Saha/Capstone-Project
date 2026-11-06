"""Coding Mode: the Arena.

Problems are verified (reference vs brute force) once per process before they are
served. Hidden tests come from the verified reference and never leave the backend.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from .content.seed_coding import SEED_PROBLEMS
from .progression import XP_RULES, award
from .store import Store, new_id, now_iso
from .verification.coding_engine import (
    CodingProblemSpec,
    CodingVerification,
    SubmissionResult,
    grade_scale,
    grade_submission,
    verify_coding_problem,
)
from .verification.executors import HARNESS_PATH, Executor, executor_from_env
from .verification.status import VerificationStatus

log = logging.getLogger("reps.arena")

_lock = threading.Lock()
_arena: dict[str, tuple[CodingProblemSpec, CodingVerification]] | None = None


class ArenaError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _cache_dir() -> Path | None:
    if os.environ.get("REPS_ARENA_CACHE", "1") == "0":
        return None
    d = Path(os.environ.get("REPS_CACHE_DIR") or Path(__file__).resolve().parents[1] / "data" / "cache")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _verify_cached(spec: CodingProblemSpec, ex: Executor) -> CodingVerification:
    """Verification (and speed-tier calibration) is cached per machine, keyed by the
    problem, the harness and the runner, so restarts don't repeat ~15s of checks."""
    cache = _cache_dir()
    key = hashlib.sha256((spec.model_dump_json() + HARNESS_PATH.read_text() + ex.name).encode()).hexdigest()[:24]
    path = cache / f"arena-{key}.json" if cache else None
    if path and path.exists():
        try:
            return CodingVerification.model_validate_json(path.read_text())
        except ValueError:
            path.unlink(missing_ok=True)
    v = verify_coding_problem(spec, ex)
    if path and v.status is VerificationStatus.VERIFIED:
        path.write_text(v.model_dump_json())
    return v


def load(store: Store | None = None, executor: Executor | None = None) -> dict[str, tuple[CodingProblemSpec, CodingVerification]]:
    global _arena
    with _lock:
        if _arena is None:
            ex = executor or executor_from_env()
            arena = {}
            for spec in SEED_PROBLEMS:
                v = _verify_cached(spec, ex)
                if store is not None:
                    store.run(
                        "insert into verification_log (id, subject, subject_id, status, reason, method, duration_ms, created_at) "
                        "values (?, 'coding_problem', ?, ?, ?, 'reference vs brute force', ?, ?)",
                        (new_id(), slug(spec.title), v.status.value, v.reason, v.duration_ms, now_iso()),
                    )
                if v.status is VerificationStatus.VERIFIED:
                    arena[slug(spec.title)] = (spec, v)
                else:
                    log.error("problem %s failed verification: %s", spec.title, v.reason)
            _arena = arena
        return _arena


def reset() -> None:
    global _arena
    with _lock:
        _arena = None


def _get(store: Store, problem_slug: str) -> tuple[CodingProblemSpec, CodingVerification]:
    arena = load(store)
    if problem_slug not in arena:
        raise ArenaError(404, "Problem not found.")
    return arena[problem_slug]


def _fast(store: Store, problem_slug: str) -> bool:
    return bool(store.one("select 1 from xp_events where reason = 'coding_fast' and source_id = ?", (problem_slug,)))


def _status(store: Store, problem_slug: str) -> str:
    row = store.one(
        "select max(case when is_submit = 1 and verdict = 'accepted' then 1 else 0 end) solved, count(*) n from coding_submissions where slug = ?",
        (problem_slug,),
    )
    if row and row["solved"]:
        return "solved"
    return "attempted" if row and row["n"] else "new"


DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}


def list_problems(store: Store) -> list[dict[str, Any]]:
    out = []
    for s, (spec, v) in load(store).items():
        out.append(
            {
                "slug": s,
                "title": spec.title,
                "pattern": spec.pattern,
                "difficulty": spec.difficulty,
                "status": _status(store, s),
                "xp": XP_RULES[f"coding_accepted_{spec.difficulty}"],
                "verified_cases": v.cases_run,
                "fast": _fast(store, s),
            }
        )
    return sorted(out, key=lambda p: (DIFFICULTY_ORDER[p["difficulty"]], p["title"]))


def starter_code(spec: CodingProblemSpec) -> str:
    return f"{spec.signature}:\n    # Write your solution here\n    pass\n"


def js_starter_code(spec: CodingProblemSpec) -> str:
    """function solve(a, b) from def solve(a: list[int], b: int) -> int, with the Python types as a hint."""
    m = re.match(r"def\s+solve\((.*)\)\s*(?:->\s*(.+))?$", spec.signature.strip())
    params = []
    hints = []
    if m:
        for part in _split_params(m.group(1)):
            name, _, typ = part.partition(":")
            params.append(name.strip())
            if typ.strip():
                hints.append(f"{name.strip()}: {typ.strip()}")
        if m.group(2):
            hints.append(f"returns {m.group(2).strip()}")
    hint = f"  // {', '.join(hints)}\n" if hints else ""
    return f"function solve({', '.join(params)}) {{\n{hint}  // Write your solution here\n}}\n"


def _split_params(text: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in text:
        depth += ch in "[(" or 0
        depth -= ch in "])" or 0
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return [p for p in (*out, cur) if p.strip()]


def problem_detail(store: Store, problem_slug: str) -> dict[str, Any]:
    spec, v = _get(store, problem_slug)
    last = store.one("select code from coding_submissions where slug = ? and language = 'python' order by created_at desc limit 1", (problem_slug,))
    last_js = store.one("select code from coding_submissions where slug = ? and language = 'javascript' order by created_at desc limit 1", (problem_slug,))
    history = store.all(
        "select verdict, scale, passed, total, is_submit, runtime_ms, language, created_at from coding_submissions where slug = ? order by created_at desc limit 10",
        (problem_slug,),
    )
    return {
        "slug": problem_slug,
        "title": spec.title,
        "pattern": spec.pattern,
        "difficulty": spec.difficulty,
        "statement": spec.statement,
        "signature": spec.signature,
        "examples": [{"args": t.args, "expected": t.expected} for t in v.tests if not t.hidden],
        "hidden_tests": sum(1 for t in v.tests if t.hidden),
        "starter_code": starter_code(spec),
        "starter_code_js": js_starter_code(spec),
        "languages": ["python", "javascript"],
        "saved_code": last["code"] if last else None,
        "saved_code_js": last_js["code"] if last_js else None,
        "status": _status(store, problem_slug),
        "xp": XP_RULES[f"coding_accepted_{spec.difficulty}"],
        "verification": {"cases_run": v.cases_run, "method": "reference vs independent brute force", "seed": v.seed},
        "speed_tier": {"limit_ms": v.scale.limit_ms, "reference_ms": round(v.scale.reference_ms, 1)} if v.scale else None,
        "fast": _fast(store, problem_slug),
        "history": [{**h, "is_submit": bool(h["is_submit"])} for h in history],
    }


def grade(store: Store, problem_slug: str, code: str, language: str, submit: bool) -> dict[str, Any]:
    if language not in ("python", "javascript"):
        raise ArenaError(422, "Python and JavaScript are supported.")
    spec, v = _get(store, problem_slug)
    executor = executor_from_env()
    result: SubmissionResult = grade_submission(code, v.tests, executor, include_hidden=submit, unordered=spec.unordered_output, language=language)
    sub_id = new_id()
    store.run(
        "insert into coding_submissions (id, slug, code, is_submit, verdict, passed, total, runtime_ms, executor, language, created_at) "
        "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sub_id, problem_slug, code, int(submit), result.verdict, result.passed, result.total, result.runtime_ms, result.executor, language, now_iso()),
    )
    xp = 0
    if submit and result.verdict == "accepted":
        # One award per problem, ever: source is the problem, not the submission.
        xp = award(store, f"coding_accepted_{spec.difficulty}", XP_RULES[f"coding_accepted_{spec.difficulty}"], "coding_problem", problem_slug)
        if v.scale and language == "python":  # speed tiers are calibrated against the Python reference
            result.scale = grade_scale(code, spec, v.scale, executor)
            if result.scale.status == "fast":
                xp += award(store, "coding_fast", XP_RULES["coding_fast"], "coding_problem", problem_slug)
            store.run("update coding_submissions set scale = ? where id = ?", (result.scale.status, sub_id))
    return {**result.model_dump(), "xp": xp, "submission_id": sub_id, "status": _status(store, problem_slug)}
