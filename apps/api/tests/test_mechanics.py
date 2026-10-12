import random

import pytest

from reps_api import exam
from reps_api.tutor.knowledge_tracing import DEFAULT_PARAMS, decayed, half_life_days
from reps_api.verification.math_engine import MathTask
from reps_api.verification.steps import check_steps, final_answer


def _key(store, qid):
    return store.one("select answer from exam_questions where id = ?", (qid,))["answer"]


def _ask(store, sid, rng):
    return exam.next_question(store, sid, rng=rng, use_pool=False)["current_question"]


# ------------------------------------------------------------------ rematch


def test_missed_question_returns_with_new_numbers(store):
    rng = random.Random(3)
    s = exam.start_session(store, "calc-1")
    first = _ask(store, s["id"], rng)
    exam.submit_answer(store, s["id"], first["id"], "424242", use_pool=False)
    seen = []
    for _ in range(4):
        q = _ask(store, s["id"], rng)
        seen.append(q)
        exam.submit_answer(store, s["id"], q["id"], _key(store, q["id"]), use_pool=False)
    rematches = [q for q in seen if q["rematch"]]
    assert len(rematches) == 1
    rm = store.one("select * from exam_questions where id = ?", (rematches[0]["id"],))
    orig = store.one("select * from exam_questions where id = ?", (first["id"],))
    assert rm["rematch_of"] == first["id"] and rm["template_id"] == orig["template_id"] and rm["seed"] != orig["seed"]
    assert seen.index(rematches[0]) >= exam.REMATCH_GAP  # not immediately
    assert store.one("select count(*) n from xp_events where reason = 'rematch_redeemed'")["n"] == 1


# ------------------------------------------------------------------ show your work


def test_steps_locate_the_first_wrong_line():
    task = MathTask(kind="derivative", expr="sin(4*x^2)")
    r = check_steps(task, "8*x*cos(4*x**2)", ["cos(4x^2) * 4x", "4x cos(4x^2)"])
    assert r.first_error == 0 and "factor of 1/2" in r.lines[0].note


def test_steps_catch_arithmetic_and_lost_solutions():
    r = check_steps(MathTask(kind="integral_definite", expr="9*x^2", lower="0", upper="5"), "375", ["3x^3", "3*5^3 = 365"])
    assert r.first_error == 1 and "375, not 365" in r.lines[1].note
    r = check_steps(MathTask(kind="solve", expr="x^2 - 9"), "-3, 3", ["x^2 = 9", "x = 3"])
    assert r.first_error == 1 and "-3 also works" in r.lines[1].note


def test_steps_accept_good_work_and_skip_definitions():
    task = MathTask(kind="integral_indefinite", expr="x*exp(2*x)")
    r = check_steps(task, "x*exp(2*x)/2 - exp(2*x)/4", ["u = x", "dv = e^(2x)", "x e^(2x)/2 - e^(2x)/4 + 3"])
    assert r.first_error is None and [ln.status for ln in r.lines] == ["unchecked", "unchecked", "ok"]
    r = check_steps(MathTask(kind="limit", expr="(x^2-9)/(x-3)", at="3"), "6", ["(x-3)(x+3)/(x-3)", "x + 3", "3 + 3 = 6"])
    assert r.first_error is None and [ln.role for ln in r.lines] == ["problem", "problem", "answer"]


def test_final_answer_is_the_last_segment():
    assert final_answer(MathTask(kind="evaluate", expr="1"), ["d = v t", "d = 7*75 = 525"]) == "525"
    assert final_answer(MathTask(kind="solve", expr="x"), ["x = 3 or x = -3"]) == "x = 3 or x = -3"


def test_shown_work_is_graded_and_rewarded(store):
    s = exam.start_session(store, "phys-kinematics")
    q = _ask(store, s["id"], random.Random(2))
    key = _key(store, q["id"])
    out = exam.submit_answer(store, s["id"], q["id"], "", steps=[f"= {key}", f"{key}"], use_pool=False)
    assert out["correct"] and out["steps"]["first_error"] is None
    assert store.one("select count(*) n from xp_events where reason = 'clean_work'")["n"] == 1


# ------------------------------------------------------------------ forgetting


def test_forgetting_curve():
    assert decayed(0.9, 0, 3) == 0.9
    assert decayed(0.2, 30, 0) == 0.2  # never raises a low estimate
    one_half_life = decayed(0.9, half_life_days(0), 0)
    assert one_half_life == pytest.approx(DEFAULT_PARAMS.p_init + 0.3)
    assert decayed(0.9, 5, 6) > decayed(0.9, 5, 1)  # more practice, slower fade


def test_boss_regains_hp_while_you_are_away(store):
    rng = random.Random(4)
    s = exam.start_session(store, "phys-kinematics")
    for _ in range(3):
        q = _ask(store, s["id"], rng)
        exam.submit_answer(store, s["id"], q["id"], _key(store, q["id"]), use_pool=False)
    exam.retreat(store, s["id"])
    hp_now = next(c for c in exam.list_courses(store) if c["id"] == "phys-kinematics")["hp"]
    store.run("update topic_mastery set updated_at = '2026-01-01T00:00:00+00:00'")
    hp_later = next(c for c in exam.list_courses(store) if c["id"] == "phys-kinematics")["hp"]
    assert hp_later > hp_now


# ------------------------------------------------------------------ daily raid


def test_raid_needs_history_then_targets_fading_topics_once_a_day(store):
    with pytest.raises(exam.ExamError):
        exam.start_raid(store)
    rng = random.Random(6)
    s = exam.start_session(store, "calc-1")
    for _ in range(6):
        q = _ask(store, s["id"], rng)
        exam.submit_answer(store, s["id"], q["id"], _key(store, q["id"]), use_pool=False)
    exam.retreat(store, s["id"])
    limits = "calc-1:limits"
    store.run("update topic_mastery set updated_at = '2026-01-01T00:00:00+00:00' where topic_id = ?", (limits,))
    preview = exam.raid_preview(store)
    assert preview["available"] and preview["topics"][0]["id"] == limits
    raid = exam.start_raid(store)
    assert raid["kind"] == "raid" and raid["max_hearts"] == exam.RAID_HEARTS and raid["question_target"] == exam.RAID_LENGTH
    for _ in range(exam.RAID_LENGTH):
        q = _ask(store, raid["id"], rng)
        out = exam.submit_answer(store, raid["id"], q["id"], _key(store, q["id"]), use_pool=False)
    assert out["session"]["outcome"] == "victory"
    assert store.one("select count(*) n from xp_events where reason = 'raid_cleared'")["n"] == 1
    with pytest.raises(exam.ExamError, match="tomorrow"):
        exam.start_raid(store)
    assert "daily-raid" not in {c["id"] for c in exam.list_courses(store)}


# ------------------------------------------------------------------ phases and abilities


def test_ability_topic_costs_two_hearts(store):
    s = exam.start_session(store, "calc-1")
    assert s["ability"]["topic_id"] == "calc-1:limits"
    rng = random.Random(1)
    for _ in range(6):
        q = _ask(store, s["id"], rng)
        out = exam.submit_answer(store, s["id"], q["id"], "424242", use_pool=False)
        expected = 2 if q["topic_id"] == "calc-1:limits" else 1
        assert out["hearts_lost"] == expected
        if expected == 2:
            assert out["ability_triggered"] == "Limitless Gaze"
        if out["session"]["status"] != "active":
            break


def test_phase_two_at_half_hp_asks_harder_questions(store):
    rng = random.Random(8)
    s = exam.start_session(store, "phys-kinematics")
    changed = None
    for _ in range(6):
        q = _ask(store, s["id"], rng)
        out = exam.submit_answer(store, s["id"], q["id"], _key(store, q["id"]), use_pool=False)
        if out["phase_change"]:
            changed = out
            break
    assert changed and changed["session"]["phase"] == 2 and changed["session"]["hp"] <= exam.PHASE2_HP


# ------------------------------------------------------------------ achievements


def test_achievements_unlock_once_from_real_events(store):
    from reps_api import achievements, player

    assert achievements.check(store) == []
    rng = random.Random(4)
    s = exam.start_session(store, "phys-kinematics")
    while True:
        q = _ask(store, s["id"], rng)
        out = exam.submit_answer(store, s["id"], q["id"], _key(store, q["id"]), use_pool=False)
        if out["session"]["status"] != "active":
            break
    summary = player.summary(store)
    keys = {a["key"] for a in summary["new_achievements"]}
    assert {"first_hit", "first_boss", "flawless", "no_hints"} <= keys
    xp_before = summary["xp"]
    assert achievements.check(store) == []  # nothing twice
    achievements.mark_seen(store, list(keys))
    again = player.summary(store)
    assert again["new_achievements"] == [] and again["xp"] == xp_before
    assert store.one("select count(*) n from xp_events where reason = 'achievement'")["n"] == len(keys)
