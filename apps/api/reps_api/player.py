"""The player hub: level, XP, streaks, weak topics, and where to continue."""

from __future__ import annotations

from typing import Any

from .progression import level_for, streaks
from .store import Store
from .tutor.knowledge_tracing import MIN_EVIDENCE


def summary(store: Store) -> dict[str, Any]:
    player = store.one("select display_name, created_at from player where id = 1")
    total = store.one("select coalesce(sum(amount), 0) n from xp_events")["n"]
    lvl = level_for(total)
    days = [r["local_day"] for r in store.all("select distinct local_day from xp_events")]
    current, best = streaks(days)
    today = store.one("select coalesce(sum(amount), 0) n from xp_events where local_day = (select max(local_day) from xp_events)")

    weak = store.all(
        "select t.id, t.name, c.name course, c.id course_id, m.p_known, m.attempts from topic_mastery m "
        "join topics t on t.id = m.topic_id join courses c on c.id = t.course_id where m.attempts > 0 order by m.p_known asc limit 5"
    )
    active_exam = store.one(
        "select s.id, s.boss_name, s.hp_current, c.name course from exam_sessions s join courses c on c.id = s.course_id "
        "where s.status = 'active' order by s.started_at desc limit 1"
    )
    unsolved = store.one(
        "select slug, max(created_at) last from coding_submissions where slug not in "
        "(select slug from coding_submissions where is_submit = 1 and verdict = 'accepted') group by slug order by last desc limit 1"
    )
    active_interview = store.one("select id, role, started_at from interview_sessions where status = 'active' order by started_at desc limit 1")
    recent = store.all("select reason, amount, created_at from xp_events order by created_at desc limit 8")

    return {
        "name": player["display_name"],
        "level": lvl.level,
        "xp": lvl.total_xp,
        "xp_into_level": lvl.into_level,
        "xp_for_next": lvl.needed,
        "streak": current,
        "best_streak": best,
        "practiced_today": bool(days) and current > 0 and today["n"] > 0,
        "stats": {
            "bosses_defeated": store.one("select count(*) n from exam_sessions where outcome = 'victory'")["n"],
            "fights": store.one("select count(*) n from exam_sessions where status = 'completed'")["n"],
            "questions_answered": store.one("select count(*) n from exam_attempts")["n"],
            "problems_solved": store.one("select count(distinct slug) n from coding_submissions where is_submit = 1 and verdict = 'accepted'")["n"],
            "interviews": store.one("select count(*) n from interview_sessions where status = 'completed'")["n"],
        },
        "weak_topics": [
            {
                "id": w["id"],
                "name": w["name"],
                "course": w["course"],
                "course_id": w["course_id"],
                "mastery": round(w["p_known"], 3),
                "attempts": w["attempts"],
                "provisional": w["attempts"] < MIN_EVIDENCE,
            }
            for w in weak
        ],
        "continue": {
            "exam": active_exam,
            "coding": unsolved,
            "interview": active_interview,
        },
        "recent_xp": recent,
        "xp_rules": "XP comes from verified correct answers, accepted solutions and finished sessions. It's motivation, not a grade.",
    }


def rename(store: Store, name: str) -> dict[str, Any]:
    store.run("update player set display_name = ? where id = 1", (name.strip()[:40] or "Player",))
    return summary(store)
