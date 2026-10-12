"""Coding Mode: the Arena.

Problems are verified (reference vs brute force) once per process before they are
served. Hidden tests come from the verified reference and never leave the backend.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from .content.seed_coding import SEED_PROBLEMS
from .progression import XP_RULES, award
from .store import Store, new_id, now_iso
from .verification.coding_engine import CodingProblemSpec, CodingVerification, SubmissionResult, grade_submission, verify_coding_problem
from .verification.executors import Executor, executor_from_env
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


def load(store: Store | None = None, executor: Executor | None = None) -> dict[str, tuple[CodingProblemSpec, CodingVerification]]:
    global _arena
    with _lock:
        if _arena is None:
            ex = executor or executor_from_env()
            arena = {}
            for spec in SEED_PROBLEMS:
                v = verify_coding_problem(spec, ex)
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
            }
        )
    return sorted(out, key=lambda p: (DIFFICULTY_ORDER[p["difficulty"]], p["title"]))


def starter_code(spec: CodingProblemSpec) -> str:
    return f"{spec.signature}:\n    # Write your solution here\n    pass\n"


def problem_detail(store: Store, problem_slug: str) -> dict[str, Any]:
    spec, v = _get(store, problem_slug)
    last = store.one("select code from coding_submissions where slug = ? order by created_at desc limit 1", (problem_slug,))
    history = store.all(
        "select verdict, passed, total, is_submit, runtime_ms, created_at from coding_submissions where slug = ? order by created_at desc limit 10",
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
        "saved_code": last["code"] if last else None,
        "status": _status(store, problem_slug),
        "xp": XP_RULES[f"coding_accepted_{spec.difficulty}"],
        "verification": {"cases_run": v.cases_run, "method": "reference vs independent brute force", "seed": v.seed},
        "history": [{**h, "is_submit": bool(h["is_submit"])} for h in history],
    }


def grade(store: Store, problem_slug: str, code: str, language: str, submit: bool) -> dict[str, Any]:
    if language != "python":
        raise ArenaError(422, "Only Python is supported right now.")
    spec, v = _get(store, problem_slug)
    executor = executor_from_env()
    result: SubmissionResult = grade_submission(code, v.tests, executor, include_hidden=submit, unordered=spec.unordered_output)
    sub_id = new_id()
    store.run(
        "insert into coding_submissions (id, slug, code, is_submit, verdict, passed, total, runtime_ms, executor, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sub_id, problem_slug, code, int(submit), result.verdict, result.passed, result.total, result.runtime_ms, result.executor, now_iso()),
    )
    xp = 0
    if submit and result.verdict == "accepted":
        # One award per problem, ever: source is the problem, not the submission.
        xp = award(store, f"coding_accepted_{spec.difficulty}", XP_RULES[f"coding_accepted_{spec.difficulty}"], "coding_problem", problem_slug)
    return {**result.model_dump(), "xp": xp, "submission_id": sub_id, "status": _status(store, problem_slug)}
