"""Progress page data: mastery history, XP by day, accuracy, verification evidence."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import achievements, exam
from .store import Store, local_day

# Same bar the boss fight uses: a topic at 75% mastery counts toward victory.
READY_MASTERY = 0.75


def summary(store: Store) -> dict[str, Any]:
    achievements.check(store)
    answered = store.one("select count(*) n, coalesce(sum(correct), 0) c from exam_attempts")
    courses = [c for c in store.all("select id, name, code from courses where id != ? order by kind, created_at", (exam.RAID_ID,))]

    # Mastery history per course: one point per graded answer on that course's topics.
    history = []
    for c in courses:
        ids = exam.course_topic_ids(store, c["id"])
        if not ids:
            continue
        marks = ",".join("?" * len(ids))
        events = store.all(
            f"select topic_id, p_before, p_after, correct, created_at from mastery_events where topic_id in ({marks}) order by created_at",
            tuple(ids),
        )
        if not events:
            continue
        names = {t["id"]: t["name"] for t in exam.topic_view(store, ids)}
        history.append(
            {
                "course_id": c["id"],
                "course": c["name"],
                "topics": [{"id": t, "name": names[t]} for t in ids],
                "events": [
                    {
                        "i": i + 1,
                        "topic_id": e["topic_id"],
                        "before": round(e["p_before"], 3),
                        "after": round(e["p_after"], 3),
                        "correct": bool(e["correct"]),
                        "at": e["created_at"],
                    }
                    for i, e in enumerate(events)
                ],
                "now": {t["id"]: t["mastery"] for t in exam.topic_view(store, ids)},
            }
        )

    # XP per local day, last 14 days including today.
    today = date.fromisoformat(local_day())
    days = [(today - timedelta(days=13 - i)).isoformat() for i in range(14)]
    xp_rows = {r["local_day"]: r["n"] for r in store.all("select local_day, sum(amount) n from xp_events group by local_day")}
    xp_by_day = [{"day": d, "xp": int(xp_rows.get(d, 0))} for d in days]

    accuracy = store.all(
        "select c.name course, count(*) answered, sum(a.correct) correct from exam_attempts a join exam_questions q on q.id = a.question_id "
        "join topics t on t.id = q.topic_id join courses c on c.id = t.course_id group by c.id order by answered desc"
    )

    # Readiness per course: forgetting-adjusted mastery, with the topics that still need work.
    readiness = []
    for c in courses:
        ids = exam.course_topic_ids(store, c["id"])
        if not ids:
            continue
        topics = exam.topic_view(store, ids)
        avg = sum(t["mastery"] for t in topics) / len(topics)
        weakest = sorted(topics, key=lambda t: t["mastery"])[:3]
        readiness.append(
            {
                "course_id": c["id"],
                "course": c["name"],
                "readiness": round(avg, 3),
                "ready_topics": sum(1 for t in topics if t["mastery"] >= READY_MASTERY),
                "total_topics": len(topics),
                "fading_topics": sum(1 for t in topics if t["fading"] >= 0.05),
                "weakest": [
                    {
                        "name": t["name"],
                        "mastery": t["mastery"],
                        "attempts": t["attempts"],
                        "accuracy": round(t["correct"] / t["attempts"], 3) if t["attempts"] else None,
                    }
                    for t in weakest
                ],
            }
        )

    verification = {}
    for row in store.all("select subject, status, count(*) n from verification_log group by subject, status"):
        verification.setdefault(row["subject"], {})[row["status"]] = row["n"]
    reasons = store.all(
        "select subject, reason, count(*) n from verification_log where status != 'verified' and reason is not null group by subject, reason order by n desc limit 8"
    )

    return {
        "totals": {
            "answered": answered["n"],
            "correct": answered["c"],
            "accuracy": round(answered["c"] / answered["n"], 3) if answered["n"] else None,
            "fights": store.one("select count(*) n from exam_sessions where status = 'completed' and kind = 'course'")["n"],
            "raids": store.one("select count(*) n from exam_sessions where status = 'completed' and kind = 'raid'")["n"],
            "problems_solved": store.one("select count(distinct slug) n from coding_submissions where is_submit = 1 and verdict = 'accepted'")["n"],
            "interviews": store.one("select count(*) n from interview_sessions where status = 'completed'")["n"],
            "clean_work": store.one("select count(*) n from xp_events where reason = 'clean_work'")["n"],
        },
        "mastery_history": history,
        "xp_by_day": xp_by_day,
        "readiness": readiness,
        "accuracy_by_course": [{**r, "correct": int(r["correct"] or 0)} for r in accuracy],
        "verification": verification,
        "rejection_reasons": reasons,
        "achievements": achievements.listing(store),
    }
