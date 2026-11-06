"""Exam Mode: boss fights over a course's topics, and the cross-course Daily Raid.

Rules of a boss fight
  * Boss HP = 100 x (1 - mean mastery) over the course's topics. Mastery is the BKT
    estimate with forgetting applied, so a boss regains HP on topics you haven't
    practised in a while. HP moves only after the backend grades an answer.
  * You win at VICTORY_HP or below (75% average mastery). 5 hearts; a wrong answer
    costs one, or two on the topic tied to the boss's ability.
  * At PHASE2_HP the boss enters phase 2 and asks harder questions.
  * A question you miss comes back later in the fight with new numbers (a rematch).
  * At most `question_target` questions.

The Daily Raid is a 5-question fight across every course, aimed at the topics
fading fastest. 3 hearts, once per day.
"""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime
from typing import Any

from . import recall
from .content.courses import BUILTIN_COURSES, QuestionTemplate
from .progression import XP_RULES, award, exam_correct_xp
from .store import Store, dumps, loads, local_day, new_id, now_iso
from .tutor.knowledge_tracing import (
    DEFAULT_PARAMS,
    FORGETTING_VERSION,
    MODEL_VERSION,
    BossPolicy,
    TopicMastery,
    boss_hp,
    decayed,
    half_life_days,
)
from .verification.math_engine import MathTask, MathVerification, display_latex, grade_answer, verify_problem
from .verification.status import VerificationStatus
from .verification.steps import StepReport, check_steps, final_answer
from .verification.timeouts import VerificationTimeout, run_with_timeout

VICTORY_HP = 25
PHASE2_HP = 50
START_HEARTS = 5
DEFAULT_LENGTH = 15
MAX_INSTANCE_TRIES = 4
REMATCH_GAP = 2  # a missed question returns after at least this many others

RAID_ID = "daily-raid"
RAID_BOSS = "The Fading"
RAID_LENGTH = 5
RAID_HEARTS = 3
RAID_TOPICS = 5
RAID_WIN_CORRECT = 3

_BUILTIN = {c.id: c for c in BUILTIN_COURSES}


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
                "insert into courses (id, name, code, boss_name, kind, created_at) values (?, ?, ?, ?, 'builtin', ?) "
                "on conflict (id) do update set name = excluded.name, code = excluded.code, boss_name = excluded.boss_name",
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
        # The raid is a session over topics from many courses; it hangs off this row.
        db.execute(
            "insert or ignore into courses (id, name, code, boss_name, kind, created_at) values (?, 'Daily Raid', null, ?, 'builtin', ?)",
            (RAID_ID, RAID_BOSS, now_iso()),
        )


def _days_since(iso: str | None) -> float:
    if not iso:
        return 0.0
    then = datetime.fromisoformat(iso)
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - then).total_seconds() / 86400)


def course_topic_ids(store: Store, course_id: str) -> list[str]:
    return [r["id"] for r in store.all("select id from topics where course_id = ? order by position", (course_id,))]


def _rows(store: Store, topic_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not topic_ids:
        return {}
    marks = ",".join("?" * len(topic_ids))
    rows = store.all(
        f"select t.id, t.name, t.description, c.name course, c.id course_id, m.p_known, m.attempts, m.correct, m.updated_at "
        f"from topics t join courses c on c.id = t.course_id left join topic_mastery m on m.topic_id = t.id where t.id in ({marks})",
        tuple(topic_ids),
    )
    return {r["id"]: r for r in rows}


def _effective(row: dict[str, Any]) -> tuple[float, float]:
    """(effective, recorded) mastery for a topic row."""
    raw = row["p_known"] if row["p_known"] is not None else DEFAULT_PARAMS.p_init
    return decayed(raw, _days_since(row["updated_at"]), row["correct"] or 0), raw


def _mastery(store: Store, topic_ids: list[str]) -> list[TopicMastery]:
    rows = _rows(store, topic_ids)
    out = []
    for tid in topic_ids:
        r = rows[tid]
        eff, _ = _effective(r)
        out.append(TopicMastery(topic_id=tid, p_known=eff, attempts=r["attempts"] or 0, correct=r["correct"] or 0))
    return out


def topic_view(store: Store, topic_ids: list[str], with_course: bool = False) -> list[dict[str, Any]]:
    rows = _rows(store, topic_ids)
    out = []
    for tid in topic_ids:
        r = rows[tid]
        eff, raw = _effective(r)
        attempts = r["attempts"] or 0
        out.append(
            {
                "id": tid,
                "name": r["name"],
                "description": r["description"],
                "course": r["course"] if with_course else None,
                "mastery": round(eff, 3),
                "recorded": round(raw, 3),
                "fading": round(raw - eff, 3),
                "half_life_days": round(half_life_days(r["correct"] or 0), 1) if attempts else None,
                "attempts": attempts,
                "correct": r["correct"] or 0,
                "provisional": attempts < 3,
            }
        )
    return out


def ability(store: Store, course_id: str) -> dict[str, Any] | None:
    course = _BUILTIN.get(course_id)
    if not course or not course.ability:
        return None
    tid = f"{course.id}:{course.ability.topic}"
    topic = next((t for t in course.topics if t.key == course.ability.topic), None)
    return {"name": course.ability.name, "text": course.ability.text, "topic_id": tid, "topic": topic.name if topic else None}


def list_courses(store: Store) -> list[dict[str, Any]]:
    courses = store.all("select * from courses where id != ? order by kind, created_at", (RAID_ID,))
    out = []
    for c in courses:
        ids = course_topic_ids(store, c["id"])
        active = store.one("select id from exam_sessions where course_id = ? and status = 'active' order by started_at desc", (c["id"],))
        wins = store.one("select count(*) n from exam_sessions where course_id = ? and outcome = 'victory'", (c["id"],))
        fights = store.one("select count(*) n from exam_sessions where course_id = ? and status = 'completed'", (c["id"],))
        n_templates = store.one("select count(*) n from templates where course_id = ?", (c["id"],))
        n_notes = store.one('select count(*) n from templates where course_id = ? and body like \'{"kind":"recall"%\'', (c["id"],))
        out.append(
            {
                "id": c["id"],
                "name": c["name"],
                "code": c["code"],
                "kind": c["kind"],
                "boss_name": c["boss_name"],
                "hp": boss_hp(_mastery(store, ids)),
                "topics": topic_view(store, ids),
                "question_types": n_templates["n"],
                "from_notes": n_notes["n"],
                "active_session_id": active["id"] if active else None,
                "victories": wins["n"],
                "fights": fights["n"],
                "ability": ability(store, c["id"]),
            }
        )
    return out


# ------------------------------------------------------------------ sessions


def _session(store: Store, session_id: str) -> dict[str, Any]:
    s = store.one("select * from exam_sessions where id = ?", (session_id,))
    if not s:
        raise ExamError(404, "That fight doesn't exist.")
    return s


def _scope(store: Store, s: dict[str, Any]) -> list[str]:
    if s["kind"] == "raid":
        return loads(s["topic_ids"]) or []
    return course_topic_ids(store, s["course_id"])


def _create(store: Store, course_id: str, boss: str, topic_ids: list[str], hearts: int, length: int, kind: str) -> str:
    mastery = _mastery(store, topic_ids)
    hp = boss_hp(mastery)
    sid = new_id()
    store.run(
        "insert into exam_sessions (id, course_id, status, boss_name, hp_start, hp_current, hearts, question_target, mastery_start, kind, topic_ids, "
        "phase, raid_day, started_at) values (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sid,
            course_id,
            boss,
            hp,
            hp,
            hearts,
            length,
            dumps({m.topic_id: m.p_known for m in mastery}),
            kind,
            dumps(topic_ids) if kind == "raid" else None,
            2 if kind == "course" and hp <= PHASE2_HP else 1,
            local_day() if kind == "raid" else None,
            now_iso(),
        ),
    )
    return sid


def start_session(store: Store, course_id: str, length: int = DEFAULT_LENGTH) -> dict[str, Any]:
    if course_id == RAID_ID:
        return start_raid(store)
    course = store.one("select * from courses where id = ?", (course_id,))
    if not course:
        raise ExamError(404, "Course not found.")
    if not store.one("select 1 from templates where course_id = ?", (course_id,)):
        raise ExamError(409, "This course has no verified questions yet.")
    active = store.one("select id from exam_sessions where course_id = ? and status = 'active'", (course_id,))
    if active:
        return session_state(store, active["id"])
    sid = _create(store, course_id, course["boss_name"], course_topic_ids(store, course_id), START_HEARTS, length, "course")
    return session_state(store, sid)


# ------------------------------------------------------------------ daily raid


def _raid_candidates(store: Store) -> list[dict[str, Any]]:
    """Practised topics that have questions, ranked by how much they've faded
    plus how weak they are now."""
    rows = store.all(
        "select distinct m.topic_id id from topic_mastery m join templates tp on tp.topic_id = m.topic_id where m.attempts > 0",
    )
    ids = [r["id"] for r in rows]
    view = topic_view(store, ids, with_course=True)
    for t in view:
        t["score"] = round(t["fading"] + 0.5 * (1 - t["mastery"]), 4)
    return sorted(view, key=lambda t: -t["score"])


def raid_preview(store: Store) -> dict[str, Any]:
    today = local_day()
    s = store.one("select id, status, outcome from exam_sessions where kind = 'raid' and raid_day = ? order by started_at desc", (today,))
    picks = _raid_candidates(store)[:RAID_TOPICS]
    return {
        "available": bool(picks) and (s is None or s["status"] == "active"),
        "session_id": s["id"] if s else None,
        "status": s["status"] if s else None,
        "outcome": s["outcome"] if s else None,
        "topics": picks,
        "length": RAID_LENGTH,
        "hearts": RAID_HEARTS,
        "xp": XP_RULES["raid_cleared"],
    }


def start_raid(store: Store) -> dict[str, Any]:
    today = local_day()
    existing = store.one("select id, status from exam_sessions where kind = 'raid' and raid_day = ? order by started_at desc", (today,))
    if existing and existing["status"] == "active":
        return session_state(store, existing["id"])
    if existing:
        raise ExamError(409, "Today's raid is done. A new one opens tomorrow.")
    picks = _raid_candidates(store)[:RAID_TOPICS]
    if not picks:
        raise ExamError(409, "Fight a boss first so the raid knows what you've learned.")
    sid = _create(store, RAID_ID, RAID_BOSS, [t["id"] for t in picks], RAID_HEARTS, RAID_LENGTH, "raid")
    return session_state(store, sid)


# ------------------------------------------------------------------ state


def _public_question(q: dict[str, Any], topic_name: str) -> dict[str, Any]:
    return {
        "id": q["id"],
        "topic_id": q["topic_id"],
        "topic": topic_name,
        "difficulty": q["difficulty"],
        "prompt": q["prompt"],
        "latex": q["latex"],
        "answer_format": q["answer_format"],
        "kind": _task_info(q)["kind"],
        "choices": _task_info(q).get("choices") or None,
        "hint": q["hint"] if q["hint_used"] else None,
        "hint_used": bool(q["hint_used"]),
        "rematch": q["rematch_of"] is not None,
        "verification": {"status": "verified", "checks": [c["method"] for c in loads(q["verification"])]},
    }


def session_state(store: Store, session_id: str) -> dict[str, Any]:
    s = _session(store, session_id)
    course = store.one("select name, code from courses where id = ?", (s["course_id"],))
    raid = s["kind"] == "raid"
    topics = topic_view(store, _scope(store, s), with_course=raid)
    names = {t["id"]: t["name"] for t in topics}
    asked = store.one("select count(*) n from exam_questions where session_id = ?", (session_id,))["n"]
    answered = store.all("select correct from exam_attempts where session_id = ?", (session_id,))
    pending = store.one(
        "select q.* from exam_questions q left join exam_attempts a on a.question_id = q.id where q.session_id = ? and a.id is null order by q.created_at desc limit 1",
        (session_id,),
    )
    return {
        "id": s["id"],
        "kind": s["kind"],
        "course_id": s["course_id"],
        "course_name": course["name"],
        "course_code": course["code"],
        "boss_name": s["boss_name"],
        "status": s["status"],
        "outcome": s["outcome"],
        "hp": s["hp_current"],
        "hp_start": s["hp_start"],
        "victory_hp": None if raid else VICTORY_HP,
        "phase": s["phase"],
        "phase2_hp": None if raid else PHASE2_HP,
        "ability": None if raid else ability(store, s["course_id"]),
        "hearts": s["hearts"],
        "max_hearts": RAID_HEARTS if raid else START_HEARTS,
        "combo": s["combo"],
        "best_combo": s["best_combo"],
        "question_target": s["question_target"],
        "asked": asked,
        "answered": len(answered),
        "correct": sum(r["correct"] for r in answered),
        "topics": topics,
        "current_question": _public_question(pending, names.get(pending["topic_id"], "")) if pending else None,
    }


# ------------------------------------------------------------------ questions


def _fill(text: str | None, values: dict[str, int]) -> str | None:
    if text is None:
        return None
    return re.sub(r"\{([a-z][a-z0-9]{0,7})\}", lambda m: str(values.get(m.group(1), m.group(0))), text)


def _pick_template(templates: list[tuple[str, QuestionTemplate]], target: int, recent_templates: list[str], rng: random.Random):
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


def _due_rematch(store: Store, session_id: str, history: list[dict[str, Any]]) -> dict[str, Any] | None:
    order = {h["id"]: i for i, h in enumerate(history)}
    missed = store.all(
        "select q.id, q.template_id, q.topic_id from exam_questions q join exam_attempts a on a.question_id = q.id "
        "where q.session_id = ? and a.correct = 0 and not exists (select 1 from exam_questions r where r.rematch_of = q.id) "
        "order by q.created_at",
        (session_id,),
    )
    for m in missed:
        if len(history) - 1 - order[m["id"]] >= REMATCH_GAP:
            return m
    return None


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

    scope = _scope(store, s)
    history = store.all("select id, topic_id, template_id from exam_questions where session_id = ? order by created_at", (session_id,))
    marks = ",".join("?" * len(scope))
    templates_by_topic: dict[str, list[tuple[str, QuestionTemplate]]] = {}
    for row in store.all(f"select id, topic_id, body from templates where topic_id in ({marks})", tuple(scope)):
        model = recall.RecallTemplate if recall.is_recall(row["body"]) else QuestionTemplate
        templates_by_topic.setdefault(row["topic_id"], []).append((row["id"], model.model_validate_json(row["body"])))
    mastery = [m for m in _mastery(store, scope) if m.topic_id in templates_by_topic]
    if not mastery:
        raise ExamError(409, "No verified questions for these topics.")

    rematch = _due_rematch(store, session_id, history)
    if rematch and rematch["topic_id"] in templates_by_topic:
        topic_id = rematch["topic_id"]
        candidates = [t for t in templates_by_topic[topic_id] if t[0] == rematch["template_id"]] or list(templates_by_topic[topic_id])
    else:
        rematch = None
        # Coverage is per fight: topics not yet asked in this fight count as untouched.
        asked_topics = {h["topic_id"] for h in history}
        policy_view = [m if m.topic_id in asked_topics else TopicMastery(m.topic_id, m.p_known, 0, 0) for m in mastery]
        topic_id = BossPolicy(rng=rng).next_topic(policy_view, [h["topic_id"] for h in history])
        candidates = list(templates_by_topic[topic_id])

    p_known = next(m.p_known for m in mastery if m.topic_id == topic_id)
    target = 1 if p_known < 0.45 else 2 if p_known < 0.75 else 3
    if s["phase"] >= 2:
        target = min(3, target + 1)  # phase 2: the boss hits harder
    recent_templates = [h["template_id"] for h in history]

    while candidates:
        template_id, tpl = _pick_template(candidates, target, [] if rematch else recent_templates, rng)
        if isinstance(tpl, recall.RecallTemplate):
            _insert_recall(store, session_id, topic_id, template_id, tpl, rematch, rng)
            return session_state(store, session_id)
        for _ in range(MAX_INSTANCE_TRIES):
            seed = rng.randrange(1, 2**31)
            result = _verify(tpl.spec, seed, use_pool)
            _log_verification(store, template_id, result)
            if result.status is VerificationStatus.VERIFIED and result.instance and result.answer:
                values = result.instance.values
                store.run(
                    "insert into exam_questions (id, session_id, topic_id, template_id, seed, difficulty, prompt, latex, task, answer, answer_latex, "
                    "rel_tol, hint, method, answer_format, verification, rematch_of, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        rematch["id"] if rematch else None,
                        now_iso(),
                    ),
                )
                return session_state(store, session_id)
        candidates = [c for c in candidates if c[0] != template_id]
    raise ExamError(503, "Couldn't produce a verified question for this topic. The failure was logged.")


def _insert_recall(store: Store, session_id: str, topic_id: str, template_id: str, tpl: recall.RecallTemplate, rematch, rng: random.Random) -> None:
    choices = list(tpl.choices)
    rng.shuffle(choices)
    pages = ", ".join(str(p) for p in tpl.pages)
    store.run(
        "insert into exam_questions (id, session_id, topic_id, template_id, seed, difficulty, prompt, latex, task, answer, answer_latex, "
        "rel_tol, hint, method, answer_format, verification, rematch_of, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            new_id(),
            session_id,
            topic_id,
            template_id,
            0,
            tpl.difficulty,
            tpl.prompt,
            None,
            dumps({"kind": "recall", "form": tpl.form, "choices": choices, "accept": tpl.accept}),
            tpl.answer,
            None,
            None,
            f"Starts with “{tpl.answer[:1].upper()}”, {len(tpl.answer)} characters."
            if tpl.form == "short"
            else "Look for the word that fits the grammar of the sentence.",
            f"From your notes (page {pages}): “{tpl.quote}”",
            "Pick one." if tpl.form == "mcq" else "Type the missing word or phrase. Small typos are fine.",
            dumps([{"method": f"quoted from your notes, page {pages}"}]),
            rematch["id"] if rematch else None,
            now_iso(),
        ),
    )


def _task_info(q: dict[str, Any]) -> dict[str, Any]:
    raw = loads(q["task"]) or {}
    return raw if raw.get("kind") == "recall" else {"kind": raw.get("kind")}


def use_hint(store: Store, session_id: str, question_id: str) -> dict[str, Any]:
    q = store.one("select * from exam_questions where id = ? and session_id = ?", (question_id, session_id))
    if not q:
        raise ExamError(404, "Question not found.")
    store.run("update exam_questions set hint_used = 1 where id = ?", (question_id,))
    return {"hint": q["hint"]}


# ------------------------------------------------------------------ answers


def _grade(task: MathTask, q: dict[str, Any], answer: str, steps: list[str] | None, use_pool: bool):
    def work():
        report = check_steps(task, q["answer"], steps, q["seed"], q["rel_tol"]) if steps else None
        return grade_answer(task, q["answer"], answer, q["seed"], q["rel_tol"]), report

    if not use_pool:
        return work()
    grade = run_with_timeout(grade_answer, task, q["answer"], answer, q["seed"], q["rel_tol"], timeout_s=8)
    report = None
    if steps:
        try:
            report = run_with_timeout(check_steps, task, q["answer"], steps, q["seed"], q["rel_tol"], timeout_s=12)
        except VerificationTimeout:
            report = StepReport(lines=[], first_error=None, checked=0, summary="Checking your work took too long, so it was skipped.")
    return grade, report


def submit_answer(store: Store, session_id: str, question_id: str, answer: str, steps: list[str] | None = None, use_pool: bool = True) -> dict[str, Any]:
    s = _session(store, session_id)
    q = store.one("select * from exam_questions where id = ? and session_id = ?", (question_id, session_id))
    if not q:
        raise ExamError(404, "Question not found.")
    previous = store.one("select * from exam_attempts where question_id = ?", (question_id,))
    if previous:  # retried request: return the recorded result, change nothing
        return _feedback(store, session_id, q, previous, xp=previous["xp"], replay=True)
    if s["status"] != "active":
        raise ExamError(409, "This fight is over.")

    info = _task_info(q)
    if info["kind"] == "recall":
        answer = answer.strip()
        if not answer:
            raise ExamError(422, "Pick or type an answer first.")
        grade, report = recall.grade(info, q["answer"], answer), None
    else:
        task = MathTask.model_validate_json(q["task"])
        steps = [ln for ln in (steps or []) if ln.strip()][:20] or None
        if steps:
            answer = final_answer(task, steps)
        answer = answer.strip()
        if not answer:
            raise ExamError(422, "Type an answer first.")
        try:
            grade, report = _grade(task, q, answer, steps, use_pool)
        except VerificationTimeout:
            return {"status": "unparseable", "message": "Checking that answer took too long. Try a simpler form."}
    if grade.correct is None:
        return {"status": "unparseable", "message": f"Couldn't read that answer ({grade.detail}). {q['answer_format']}."}

    correct = bool(grade.correct)
    raid = s["kind"] == "raid"
    scope = _scope(store, s)
    mastery = {m.topic_id: m for m in _mastery(store, scope)}
    before = mastery[q["topic_id"]]
    after = before.record(correct)
    mastery[q["topic_id"]] = after
    hp_before = s["hp_current"]
    hp_after = boss_hp(list(mastery.values()))
    combo = s["combo"] + 1 if correct else 0
    boss_ability = None if raid else ability(store, s["course_id"])
    ability_hit = (not correct) and boss_ability is not None and boss_ability["topic_id"] == q["topic_id"]
    hearts_lost = 0 if correct else (2 if ability_hit else 1)
    hearts = max(0, s["hearts"] - hearts_lost)
    phase = s["phase"]
    phase_change = not raid and phase == 1 and hp_after <= PHASE2_HP and hp_after > VICTORY_HP
    if phase_change:
        phase = 2
    attempt_id = new_id()

    with store.tx() as db:
        db.execute(
            "insert into topic_mastery (topic_id, p_known, attempts, correct, model_version, updated_at) values (?, ?, ?, ?, ?, ?) "
            "on conflict (topic_id) do update set p_known = excluded.p_known, attempts = excluded.attempts, correct = excluded.correct, "
            "model_version = excluded.model_version, updated_at = excluded.updated_at",
            (after.topic_id, after.p_known, after.attempts, after.correct, f"{MODEL_VERSION}+{FORGETTING_VERSION}", now_iso()),
        )
        db.execute(
            "insert into exam_attempts (id, session_id, question_id, answer, correct, method, hp_before, hp_after, p_before, p_after, steps, hearts_lost, created_at) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt_id,
                session_id,
                question_id,
                answer[:300],
                int(correct),
                grade.method,
                hp_before,
                hp_after,
                before.p_known,
                after.p_known,
                report.model_dump_json() if report else None,
                hearts_lost,
                now_iso(),
            ),
        )
        db.execute(
            "insert into mastery_events (id, topic_id, attempt_id, p_before, p_after, correct, difficulty, model_version, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id(), after.topic_id, attempt_id, before.p_known, after.p_known, int(correct), q["difficulty"], MODEL_VERSION, now_iso()),
        )
        db.execute(
            "update exam_sessions set hp_current = ?, hearts = ?, combo = ?, best_combo = max(best_combo, ?), phase = ? where id = ?",
            (hp_after, hearts, combo, combo, phase, session_id),
        )

    xp = 0
    if correct:
        xp += award(store, "exam_correct", exam_correct_xp(combo, bool(q["hint_used"])), "exam_attempt", attempt_id)
        if q["rematch_of"]:
            xp += award(store, "rematch_redeemed", XP_RULES["rematch_redeemed"], "exam_question", q["rematch_of"])
        if report and report.first_error is None and report.checked >= 2:
            xp += award(store, "clean_work", XP_RULES["clean_work"], "exam_attempt", attempt_id)
    store.run("update exam_attempts set xp = ? where id = ?", (xp, attempt_id))

    answered = store.all("select correct from exam_attempts where session_id = ?", (session_id,))
    end = None
    if raid:
        if hearts <= 0:
            end = "knocked_out"
        elif len(answered) >= s["question_target"]:
            end = "victory" if sum(r["correct"] for r in answered) >= RAID_WIN_CORRECT else "out_of_questions"
    elif hp_after <= VICTORY_HP:
        end = "victory"
    elif hearts <= 0:
        end = "knocked_out"
    elif len(answered) >= s["question_target"]:
        end = "out_of_questions"
    if end:
        xp += _finish(store, session_id, end)
    attempt = store.one("select * from exam_attempts where id = ?", (attempt_id,))
    out = _feedback(store, session_id, q, attempt, xp=xp, replay=False)
    out["phase_change"] = phase if phase_change else None
    out["ability_triggered"] = boss_ability["name"] if ability_hit and boss_ability else None
    return out


def record_practice(store: Store, topic_id: str, correct: bool, difficulty: int) -> tuple[float, float]:
    """Update mastery for an answer graded outside a fight (party raids). Returns (before, after)."""
    before = _mastery(store, [topic_id])[0]
    after = before.record(correct)
    with store.tx() as db:
        db.execute(
            "insert into topic_mastery (topic_id, p_known, attempts, correct, model_version, updated_at) values (?, ?, ?, ?, ?, ?) "
            "on conflict (topic_id) do update set p_known = excluded.p_known, attempts = excluded.attempts, correct = excluded.correct, "
            "model_version = excluded.model_version, updated_at = excluded.updated_at",
            (after.topic_id, after.p_known, after.attempts, after.correct, f"{MODEL_VERSION}+{FORGETTING_VERSION}", now_iso()),
        )
        db.execute(
            "insert into mastery_events (id, topic_id, attempt_id, p_before, p_after, correct, difficulty, model_version, created_at) "
            "values (?, ?, null, ?, ?, ?, ?, ?, ?)",
            (new_id(), topic_id, before.p_known, after.p_known, int(correct), difficulty, MODEL_VERSION, now_iso()),
        )
    return before.p_known, after.p_known


def _finish(store: Store, session_id: str, outcome: str) -> int:
    s = _session(store, session_id)
    store.run(
        "update exam_sessions set status = 'completed', outcome = ?, completed_at = ? where id = ? and status = 'active'",
        (outcome, now_iso(), session_id),
    )
    xp = award(store, "exam_session_finished", XP_RULES["exam_session_finished"], "exam_session", session_id)
    if outcome == "victory":
        if s["kind"] == "raid":
            xp += award(store, "raid_cleared", XP_RULES["raid_cleared"], "raid_day", s["raid_day"] or local_day())
        else:
            xp += award(store, "boss_defeated", XP_RULES["boss_defeated"], "exam_session", session_id)
    return xp


def retreat(store: Store, session_id: str) -> dict[str, Any]:
    s = _session(store, session_id)
    if s["status"] == "active":
        answered = store.one("select count(*) n from exam_attempts where session_id = ?", (session_id,))["n"]
        if answered == 0 and s["kind"] != "raid":
            store.run("update exam_sessions set status = 'abandoned', completed_at = ? where id = ?", (now_iso(), session_id))
        else:
            store.run("update exam_sessions set status = 'completed', outcome = 'retreated', completed_at = ? where id = ?", (now_iso(), session_id))
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
        "hearts_lost": attempt["hearts_lost"],
        "rematch": q["rematch_of"] is not None,
        "steps": loads(attempt["steps"]),
        "xp": xp,
        "session": state,
        "phase_change": None,
        "ability_triggered": None,
    }


def results(store: Store, session_id: str) -> dict[str, Any]:
    s = _session(store, session_id)
    state = session_state(store, session_id)
    start = loads(s["mastery_start"]) or {}
    rows = store.all(
        "select q.topic_id, q.prompt, q.latex, q.answer_latex, q.answer correct_answer, q.method, q.difficulty, q.hint_used, q.rematch_of, a.answer, a.correct, "
        "a.method grading_method, a.p_before, a.p_after, a.hp_before, a.hp_after, a.xp, a.steps from exam_attempts a "
        "join exam_questions q on q.id = a.question_id where a.session_id = ? order by a.created_at",
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
    xp_total = (
        store.one(
            "select coalesce(sum(xp), 0) n from exam_attempts where session_id = ?",
            (session_id,),
        )["n"]
        + store.one(
            "select coalesce(sum(amount), 0) n from xp_events where (source_type = 'exam_session' and source_id = ?) "
            "or (source_type = 'raid_day' and source_id = ? and ? = 'raid')",
            (session_id, s["raid_day"] or "", s["kind"]),
        )["n"]
    )
    review = []
    for r in rows:
        steps = loads(r.pop("steps"))
        review.append(
            {
                **r,
                "correct": bool(r["correct"]),
                "hint_used": bool(r["hint_used"]),
                "rematch": r.pop("rematch_of") is not None,
                "topic": by_topic[r["topic_id"]]["name"],
                "steps": steps,
            }
        )
    weakest = sorted(state["topics"], key=lambda t: t["mastery"])[:2]
    return {
        "session": state,
        "topics": list(by_topic.values()),
        "attempts": review,
        "xp_earned": xp_total,
        "grading": {"verified": len(rows), "ai_evaluated": 0},
        "next_steps": [f"Practice {t['name'].lower()}: mastery {round(t['mastery'] * 100)}%" for t in weakest],
    }
