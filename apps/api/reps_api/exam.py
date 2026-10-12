"""Exam Mode: boss fights over a course's topics.

Rules of the fight
  * Boss HP = 100 x (1 - mean P(known)) over the course's topics (knowledge tracing).
    It moves only after the backend grades an answer.
  * The boss wins the fight if your hearts run out (5, one lost per wrong answer).
  * You win when HP drops to VICTORY_HP or below: average mastery of 75%.
  * A fight lasts at most `question_target` questions.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

from .content.courses import BUILTIN_COURSES, QuestionTemplate
from .progression import XP_RULES, award, exam_correct_xp
from .store import Store, dumps, loads, new_id, now_iso
from .tutor.knowledge_tracing import DEFAULT_PARAMS, MODEL_VERSION, BossPolicy, TopicMastery, boss_hp
from .verification.math_engine import MathTask, MathVerification, display_latex, grade_answer, verify_problem
from .verification.status import VerificationStatus
from .verification.timeouts import VerificationTimeout, run_with_timeout

VICTORY_HP = 25
START_HEARTS = 5
DEFAULT_LENGTH = 15
MAX_INSTANCE_TRIES = 4


class ExamError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# ------------------------------------------------------------------ courses


def sync_builtin_courses(store: Store) -> None:
    with store.tx() as db:
        for course in BUILTIN_COURSES:
            db.execute(
                "insert or ignore into courses (id, name, code, boss_name, kind, created_at) values (?, ?, ?, ?, 'builtin', ?)",
                (course.id, course.name, course.code, course.boss_name, now_iso()),
            )
            for pos, topic in enumerate(course.topics):
                db.execute(
                    "insert into topics (id, course_id, name, description, position) values (?, ?, ?, ?, ?) "
                    "on conflict (id) do update set name = excluded.name, description = excluded.description, position = excluded.position",
                    (f"{course.id}:{topic.key}", course.id, topic.name, topic.description, pos),
                )
            for tpl in course.templates:
                db.execute(
                    "insert into templates (id, course_id, topic_id, difficulty, body) values (?, ?, ?, ?, ?) "
                    "on conflict (id) do update set body = excluded.body, difficulty = excluded.difficulty",
                    (f"{course.id}:{tpl.id}", course.id, f"{course.id}:{tpl.topic}", tpl.difficulty, tpl.model_dump_json()),
                )


def _mastery(store: Store, course_id: str) -> list[TopicMastery]:
    rows = store.all(
        "select t.id, m.p_known, m.attempts, m.correct from topics t left join topic_mastery m on m.topic_id = t.id where t.course_id = ? order by t.position",
        (course_id,),
    )
    return [
        TopicMastery(
            topic_id=r["id"],
            p_known=r["p_known"] if r["p_known"] is not None else DEFAULT_PARAMS.p_init,
            attempts=r["attempts"] or 0,
            correct=r["correct"] or 0,
        )
        for r in rows
    ]


def _topic_view(store: Store, course_id: str) -> list[dict[str, Any]]:
    names = {r["id"]: r for r in store.all("select id, name, description from topics where course_id = ? order by position", (course_id,))}
    out = []
    for m in _mastery(store, course_id):
        out.append(
            {
                "id": m.topic_id,
                "name": names[m.topic_id]["name"],
                "description": names[m.topic_id]["description"],
                "mastery": round(m.p_known, 3),
                "attempts": m.attempts,
                "correct": m.correct,
                "provisional": m.provisional,
            }
        )
    return out


def list_courses(store: Store) -> list[dict[str, Any]]:
    courses = store.all("select * from courses order by kind, created_at")
    out = []
    for c in courses:
        mastery = _mastery(store, c["id"])
        active = store.one("select id from exam_sessions where course_id = ? and status = 'active' order by started_at desc", (c["id"],))
        wins = store.one("select count(*) n from exam_sessions where course_id = ? and outcome = 'victory'", (c["id"],))
        fights = store.one("select count(*) n from exam_sessions where course_id = ? and status = 'completed'", (c["id"],))
        n_templates = store.one("select count(*) n from templates where course_id = ?", (c["id"],))
        out.append(
            {
                "id": c["id"],
                "name": c["name"],
                "code": c["code"],
                "kind": c["kind"],
                "boss_name": c["boss_name"],
                "hp": boss_hp(mastery),
                "topics": _topic_view(store, c["id"]),
                "question_types": n_templates["n"],
                "active_session_id": active["id"] if active else None,
                "victories": wins["n"],
                "fights": fights["n"],
            }
        )
    return out


# ------------------------------------------------------------------ sessions


def _session(store: Store, session_id: str) -> dict[str, Any]:
    s = store.one("select * from exam_sessions where id = ?", (session_id,))
    if not s:
        raise ExamError(404, "That fight doesn't exist.")
    return s


def start_session(store: Store, course_id: str, length: int = DEFAULT_LENGTH) -> dict[str, Any]:
    course = store.one("select * from courses where id = ?", (course_id,))
    if not course:
        raise ExamError(404, "Course not found.")
    if not store.one("select 1 from templates where course_id = ?", (course_id,)):
        raise ExamError(409, "This course has no verified questions yet.")
    active = store.one("select id from exam_sessions where course_id = ? and status = 'active'", (course_id,))
    if active:
        return session_state(store, active["id"])
    mastery = _mastery(store, course_id)
    hp = boss_hp(mastery)
    sid = new_id()
    store.run(
        "insert into exam_sessions (id, course_id, status, boss_name, hp_start, hp_current, hearts, question_target, mastery_start, started_at) "
        "values (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)",
        (sid, course_id, course["boss_name"], hp, hp, START_HEARTS, length, dumps({m.topic_id: m.p_known for m in mastery}), now_iso()),
    )
    return session_state(store, sid)


def _public_question(q: dict[str, Any], topic_name: str) -> dict[str, Any]:
    return {
        "id": q["id"],
        "topic_id": q["topic_id"],
        "topic": topic_name,
        "difficulty": q["difficulty"],
        "prompt": q["prompt"],
        "latex": q["latex"],
        "answer_format": q["answer_format"],
        "hint": q["hint"] if q["hint_used"] else None,
        "hint_used": bool(q["hint_used"]),
        "verification": {
            "status": "verified",
            "checks": [c["method"] for c in loads(q["verification"])],
        },
    }


def session_state(store: Store, session_id: str) -> dict[str, Any]:
    s = _session(store, session_id)
    course = store.one("select name, code from courses where id = ?", (s["course_id"],))
    topics = _topic_view(store, s["course_id"])
    names = {t["id"]: t["name"] for t in topics}
    asked = store.one("select count(*) n from exam_questions where session_id = ?", (session_id,))["n"]
    answered = store.all("select correct from exam_attempts where session_id = ?", (session_id,))
    pending = store.one(
        "select q.* from exam_questions q left join exam_attempts a on a.question_id = q.id where q.session_id = ? and a.id is null order by q.created_at desc limit 1",
        (session_id,),
    )
    return {
        "id": s["id"],
        "course_id": s["course_id"],
        "course_name": course["name"],
        "course_code": course["code"],
        "boss_name": s["boss_name"],
        "status": s["status"],
        "outcome": s["outcome"],
        "hp": s["hp_current"],
        "hp_start": s["hp_start"],
        "victory_hp": VICTORY_HP,
        "hearts": s["hearts"],
        "max_hearts": START_HEARTS,
        "combo": s["combo"],
        "best_combo": s["best_combo"],
        "question_target": s["question_target"],
        "asked": asked,
        "answered": len(answered),
        "correct": sum(r["correct"] for r in answered),
        "topics": topics,
        "current_question": _public_question(pending, names.get(pending["topic_id"], "")) if pending else None,
    }


def _fill(text: str | None, values: dict[str, int]) -> str | None:
    if text is None:
        return None
    return re.sub(r"\{([a-z][a-z0-9]{0,7})\}", lambda m: str(values.get(m.group(1), m.group(0))), text)


def _pick_template(templates: list[tuple[str, QuestionTemplate]], p_known: float, recent_templates: list[str], rng: random.Random):
    target = 1 if p_known < 0.45 else 2 if p_known < 0.75 else 3
    fresh = [t for t in templates if t[0] not in recent_templates[-3:]] or templates
    best = min(abs(t[1].difficulty - target) for t in fresh)
    return rng.choice([t for t in fresh if abs(t[1].difficulty - target) == best])


def _log_verification(store: Store, template_id: str, result: MathVerification) -> None:
    store.run(
        "insert into verification_log (id, subject, subject_id, status, reason, method, duration_ms, created_at) values (?, 'math_template', ?, ?, ?, ?, ?, ?)",
        (new_id(), template_id, result.status.value, result.reason, "symbolic+numeric", result.duration_ms, now_iso()),
    )


def _verify(spec, seed: int, use_pool: bool) -> MathVerification:
    if not use_pool:
        return verify_problem(spec, seed)
    try:
        return run_with_timeout(verify_problem, spec, seed, timeout_s=15)
    except VerificationTimeout:
        return MathVerification(status=VerificationStatus.REJECTED, reason="verification timed out")


def next_question(store: Store, session_id: str, rng: random.Random | None = None, use_pool: bool = True) -> dict[str, Any]:
    rng = rng or random.Random()
    s = _session(store, session_id)
    if s["status"] != "active":
        raise ExamError(409, "This fight is over.")
    state = session_state(store, session_id)
    if state["current_question"]:
        return state
    if state["asked"] >= s["question_target"]:
        raise ExamError(409, "No questions left in this fight.")

    history = store.all("select topic_id, template_id from exam_questions where session_id = ? order by created_at", (session_id,))
    mastery = _mastery(store, s["course_id"])
    templates_by_topic: dict[str, list[tuple[str, QuestionTemplate]]] = {}
    for row in store.all("select id, topic_id, body from templates where course_id = ?", (s["course_id"],)):
        templates_by_topic.setdefault(row["topic_id"], []).append((row["id"], QuestionTemplate.model_validate_json(row["body"])))
    mastery = [m for m in mastery if m.topic_id in templates_by_topic]

    # Session-local coverage: treat topics not yet asked in this fight as "untouched".
    asked_topics = {h["topic_id"] for h in history}
    policy_view = [m if m.topic_id in asked_topics else TopicMastery(m.topic_id, m.p_known, 0, 0) for m in mastery]
    topic_id = BossPolicy(rng=rng).next_topic(policy_view, [h["topic_id"] for h in history])
    p_known = next(m.p_known for m in mastery if m.topic_id == topic_id)
    candidates = list(templates_by_topic[topic_id])
    recent_templates = [h["template_id"] for h in history]

    while candidates:
        template_id, tpl = _pick_template(candidates, p_known, recent_templates, rng)
        for _ in range(MAX_INSTANCE_TRIES):
            seed = rng.randrange(1, 2**31)
            result = _verify(tpl.spec, seed, use_pool)
            _log_verification(store, template_id, result)
            if result.status is VerificationStatus.VERIFIED and result.instance and result.answer:
                values = result.instance.values
                store.run(
                    "insert into exam_questions (id, session_id, topic_id, template_id, seed, difficulty, prompt, latex, task, answer, answer_latex, "
                    "rel_tol, hint, method, answer_format, verification, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id(),
                        session_id,
                        topic_id,
                        template_id,
                        seed,
                        tpl.difficulty,
                        result.instance.statement,
                        display_latex(result.instance.task),
                        result.instance.task.model_dump_json(),
                        result.answer,
                        result.answer_latex,
                        tpl.rel_tol,
                        _fill(tpl.hint, values),
                        _fill(tpl.method, values),
                        tpl.answer_format,
                        dumps([c.model_dump() for c in result.checks]),
                        now_iso(),
                    ),
                )
                return session_state(store, session_id)
        candidates = [c for c in candidates if c[0] != template_id]
    raise ExamError(503, "Couldn't produce a verified question for this topic. The failure was logged.")


def use_hint(store: Store, session_id: str, question_id: str) -> dict[str, Any]:
    q = store.one("select * from exam_questions where id = ? and session_id = ?", (question_id, session_id))
    if not q:
        raise ExamError(404, "Question not found.")
    store.run("update exam_questions set hint_used = 1 where id = ?", (question_id,))
    return {"hint": q["hint"]}


@dataclass
class _Outcome:
    status: str
    outcome: str | None


def submit_answer(store: Store, session_id: str, question_id: str, answer: str, use_pool: bool = True) -> dict[str, Any]:
    s = _session(store, session_id)
    q = store.one("select * from exam_questions where id = ? and session_id = ?", (question_id, session_id))
    if not q:
        raise ExamError(404, "Question not found.")
    previous = store.one("select * from exam_attempts where question_id = ?", (question_id,))
    if previous:  # retried request: return the recorded result, change nothing
        return _feedback(store, session_id, q, previous, xp=previous["xp"], replay=True)
    if s["status"] != "active":
        raise ExamError(409, "This fight is over.")
    answer = answer.strip()
    if not answer:
        raise ExamError(422, "Type an answer first.")

    task = MathTask.model_validate_json(q["task"])
    try:
        if use_pool:
            grade = run_with_timeout(grade_answer, task, q["answer"], answer, q["seed"], q["rel_tol"], timeout_s=8)
        else:
            grade = grade_answer(task, q["answer"], answer, q["seed"], q["rel_tol"])
    except VerificationTimeout:
        return {"status": "unparseable", "message": "Checking that answer took too long. Try a simpler form."}
    if grade.correct is None:
        return {"status": "unparseable", "message": f"Couldn't read that answer ({grade.detail}). {q['answer_format']}."}

    correct = bool(grade.correct)
    mastery = {m.topic_id: m for m in _mastery(store, s["course_id"])}
    before = mastery[q["topic_id"]]
    after = before.record(correct)
    mastery[q["topic_id"]] = after
    hp_before = s["hp_current"]
    hp_after = boss_hp(list(mastery.values()))
    combo = s["combo"] + 1 if correct else 0
    hearts = s["hearts"] - (0 if correct else 1)
    attempt_id = new_id()

    with store.tx() as db:
        db.execute(
            "insert into topic_mastery (topic_id, p_known, attempts, correct, model_version, updated_at) values (?, ?, ?, ?, ?, ?) "
            "on conflict (topic_id) do update set p_known = excluded.p_known, attempts = excluded.attempts, correct = excluded.correct, "
            "model_version = excluded.model_version, updated_at = excluded.updated_at",
            (after.topic_id, after.p_known, after.attempts, after.correct, MODEL_VERSION, now_iso()),
        )
        db.execute(
            "insert into exam_attempts (id, session_id, question_id, answer, correct, method, hp_before, hp_after, p_before, p_after, created_at) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (attempt_id, session_id, question_id, answer[:300], int(correct), grade.method, hp_before, hp_after, before.p_known, after.p_known, now_iso()),
        )
        db.execute(
            "insert into mastery_events (id, topic_id, attempt_id, p_before, p_after, correct, difficulty, model_version, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id(), after.topic_id, attempt_id, before.p_known, after.p_known, int(correct), q["difficulty"], MODEL_VERSION, now_iso()),
        )
        db.execute(
            "update exam_sessions set hp_current = ?, hearts = ?, combo = ?, best_combo = max(best_combo, ?) where id = ?",
            (hp_after, hearts, combo, combo, session_id),
        )

    xp = award(store, "exam_correct", exam_correct_xp(combo, bool(q["hint_used"])), "exam_attempt", attempt_id) if correct else 0
    store.run("update exam_attempts set xp = ? where id = ?", (xp, attempt_id))

    asked = store.one("select count(*) n from exam_attempts where session_id = ?", (session_id,))["n"]
    end = None
    if hp_after <= VICTORY_HP:
        end = "victory"
    elif hearts <= 0:
        end = "knocked_out"
    elif asked >= s["question_target"]:
        end = "out_of_questions"
    if end:
        xp += _finish(store, session_id, end)
    attempt = store.one("select * from exam_attempts where id = ?", (attempt_id,))
    return _feedback(store, session_id, q, attempt, xp=xp, replay=False)


def _finish(store: Store, session_id: str, outcome: str) -> int:
    store.run(
        "update exam_sessions set status = 'completed', outcome = ?, completed_at = ? where id = ? and status = 'active'",
        (outcome, now_iso(), session_id),
    )
    xp = award(store, "exam_session_finished", XP_RULES["exam_session_finished"], "exam_session", session_id)
    if outcome == "victory":
        xp += award(store, "boss_defeated", XP_RULES["boss_defeated"], "exam_session", session_id)
    return xp


def retreat(store: Store, session_id: str) -> dict[str, Any]:
    s = _session(store, session_id)
    if s["status"] == "active":
        answered = store.one("select count(*) n from exam_attempts where session_id = ?", (session_id,))["n"]
        if answered == 0:
            store.run("update exam_sessions set status = 'abandoned', completed_at = ? where id = ?", (now_iso(), session_id))
        else:
            store.run(
                "update exam_sessions set status = 'completed', outcome = 'retreated', completed_at = ? where id = ?",
                (now_iso(), session_id),
            )
    return session_state(store, session_id)


def _feedback(store: Store, session_id: str, q: dict[str, Any], attempt: dict[str, Any], xp: int, replay: bool) -> dict[str, Any]:
    state = session_state(store, session_id)
    return {
        "status": "graded",
        "replay": replay,
        "correct": bool(attempt["correct"]),
        "grading": {"category": "verified", "method": attempt["method"]},
        "your_answer": attempt["answer"],
        "answer": q["answer"],
        "answer_latex": q["answer_latex"],
        "method": q["method"],
        "damage": attempt["hp_before"] - attempt["hp_after"],
        "mastery_before": round(attempt["p_before"], 3),
        "mastery_after": round(attempt["p_after"], 3),
        "xp": xp,
        "session": state,
    }


def results(store: Store, session_id: str) -> dict[str, Any]:
    s = _session(store, session_id)
    state = session_state(store, session_id)
    start = loads(s["mastery_start"]) or {}
    rows = store.all(
        "select q.topic_id, q.prompt, q.latex, q.answer_latex, q.method, q.difficulty, q.hint_used, a.answer, a.correct, a.method grading_method, "
        "a.p_before, a.p_after, a.hp_before, a.hp_after, a.xp from exam_attempts a join exam_questions q on q.id = a.question_id "
        "where a.session_id = ? order by a.created_at",
        (session_id,),
    )
    by_topic: dict[str, dict[str, Any]] = {}
    for t in state["topics"]:
        by_topic[t["id"]] = {**t, "asked": 0, "right": 0, "mastery_start": round(start.get(t["id"], t["mastery"]), 3)}
    for r in rows:
        bt = by_topic.get(r["topic_id"])
        if bt:
            bt["asked"] += 1
            bt["right"] += r["correct"]
    xp_total = store.one(
        "select coalesce(sum(amount), 0) n from xp_events where (source_type = 'exam_session' and source_id = ?) "
        "or (source_type = 'exam_attempt' and source_id in (select id from exam_attempts where session_id = ?))",
        (session_id, session_id),
    )["n"]
    review = [{**r, "correct": bool(r["correct"]), "hint_used": bool(r["hint_used"]), "topic": by_topic[r["topic_id"]]["name"]} for r in rows]
    weakest = sorted(state["topics"], key=lambda t: t["mastery"])[:2]
    return {
        "session": state,
        "topics": list(by_topic.values()),
        "attempts": review,
        "xp_earned": xp_total,
        "grading": {"verified": len(rows), "ai_evaluated": 0},
        "next_steps": [f"Practice {t['name'].lower()}: mastery {round(t['mastery'] * 100)}%" for t in weakest],
    }
