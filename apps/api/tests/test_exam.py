import random

import pytest

from reps_api import exam
from reps_api.content.courses import BUILTIN_COURSES
from reps_api.progression import level_for, streaks
from reps_api.verification.math_engine import verify_problem
from reps_api.verification.status import VerificationStatus


@pytest.mark.parametrize("course", BUILTIN_COURSES, ids=lambda c: c.id)
def test_every_builtin_template_verifies(course):
    for tpl in course.templates:
        for seed in (1, 2, 3):
            r = verify_problem(tpl.spec, seed)
            assert r.status is VerificationStatus.VERIFIED, (tpl.id, r.reason)


def _key(store, question_id):
    return store.one("select answer from exam_questions where id = ?", (question_id,))["answer"]


def _play(store, session_id, answer_fn, rng):
    """Play until the fight ends; returns the final feedback."""
    feedback = None
    while True:
        state = exam.next_question(store, session_id, rng=rng, use_pool=False)
        q = state["current_question"]
        assert "answer" not in q, "answer key must not be sent with the question"
        feedback = exam.submit_answer(store, session_id, q["id"], answer_fn(q), use_pool=False)
        assert feedback["status"] == "graded"
        if feedback["session"]["status"] != "active":
            return feedback


def test_perfect_fight_wins_and_persists(store):
    rng = random.Random(4)
    s = exam.start_session(store, "phys-kinematics")
    assert s["hp"] == 70 and s["hearts"] == 5  # fresh mastery 0.3 on every topic
    final = _play(store, s["id"], lambda q: _key(store, q["id"]), rng)
    assert final["session"]["outcome"] == "victory"
    assert final["session"]["hp"] <= exam.VICTORY_HP
    res = exam.results(store, s["id"])
    assert all(t["mastery"] > t["mastery_start"] for t in res["topics"] if t["asked"])
    assert res["xp_earned"] > 50  # includes the boss bonus
    # a new fight starts from the persisted mastery, not from scratch
    again = exam.start_session(store, "phys-kinematics")
    assert again["hp"] == final["session"]["hp"]


def test_wrong_answers_cost_hearts_and_heal_the_boss(store):
    rng = random.Random(1)
    s = exam.start_session(store, "calc-1")
    final = _play(store, s["id"], lambda q: "12345", rng)
    assert final["session"]["outcome"] == "knocked_out"
    assert final["session"]["hearts"] == 0
    assert final["session"]["hp"] > s["hp"]
    assert final["xp"] > 0  # session-finished XP only
    assert store.one("select count(*) n from xp_events where reason = 'exam_correct'")["n"] == 0


def test_boss_covers_topics_before_repeating(store):
    rng = random.Random(7)
    s = exam.start_session(store, "calc-1")
    seen = []
    for _ in range(6):
        q = exam.next_question(store, s["id"], rng=rng, use_pool=False)["current_question"]
        seen.append(q["topic_id"])
        exam.submit_answer(store, s["id"], q["id"], _key(store, q["id"]), use_pool=False)
    assert len(set(seen)) == 6


def test_retry_is_idempotent(store):
    s = exam.start_session(store, "calc-1")
    q = exam.next_question(store, s["id"], rng=random.Random(2), use_pool=False)["current_question"]
    first = exam.submit_answer(store, s["id"], q["id"], _key(store, q["id"]), use_pool=False)
    second = exam.submit_answer(store, s["id"], q["id"], "999", use_pool=False)
    assert second["replay"] and second["correct"] == first["correct"]
    assert store.one("select count(*) n from exam_attempts")["n"] == 1
    assert store.one("select count(*) n from xp_events")["n"] == 1


def test_unparseable_answer_is_not_graded(store):
    s = exam.start_session(store, "calc-1")
    q = exam.next_question(store, s["id"], rng=random.Random(3), use_pool=False)["current_question"]
    out = exam.submit_answer(store, s["id"], q["id"], "import os", use_pool=False)
    assert out["status"] == "unparseable"
    assert exam.session_state(store, s["id"])["hearts"] == 5


def test_hint_halves_xp(store):
    s = exam.start_session(store, "phys-kinematics")
    q = exam.next_question(store, s["id"], rng=random.Random(5), use_pool=False)["current_question"]
    hint = exam.use_hint(store, s["id"], q["id"])
    assert hint["hint"]
    out = exam.submit_answer(store, s["id"], q["id"], _key(store, q["id"]), use_pool=False)
    assert out["xp"] == 5


def test_rounded_decimal_accepted_for_word_problems(store):
    s = exam.start_session(store, "phys-kinematics")
    q = exam.next_question(store, s["id"], rng=random.Random(9), use_pool=False)["current_question"]
    from reps_api.verification.math_engine import _num, parse_math

    exact = float(_num(parse_math(_key(store, q["id"]), ())))
    out = exam.submit_answer(store, s["id"], q["id"], f"{exact * 1.004:.4g}", use_pool=False)
    assert out["correct"]


def test_resume_returns_the_same_fight(store):
    a = exam.start_session(store, "calc-1")
    b = exam.start_session(store, "calc-1")
    assert a["id"] == b["id"]
    exam.retreat(store, a["id"])
    c = exam.start_session(store, "calc-1")
    assert c["id"] != a["id"]


# ------------------------------------------------------------------ progression


def test_levels():
    assert level_for(0).level == 1
    assert level_for(99).level == 1 and level_for(100).level == 2
    lv = level_for(260)
    assert (lv.level, lv.into_level, lv.needed) == (3, 10, 200)


def test_streaks():
    assert streaks([], "2026-10-12") == (0, 0)
    assert streaks(["2026-10-10", "2026-10-11"], "2026-10-12") == (2, 2)  # yesterday still counts
    assert streaks(["2026-10-09"], "2026-10-12") == (0, 1)
    assert streaks(["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-11", "2026-10-12"], "2026-10-12") == (2, 3)
