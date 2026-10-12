"""Achievements: badges unlocked by conditions on recorded play, each worth XP once.

Every condition is a query over data the backend wrote itself (graded attempts,
accepted submissions, finished sessions), so a badge can't be unlocked by a client
claiming it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .progression import award, level_for, streaks
from .store import Store, now_iso

ACHIEVEMENT_XP = 20


@dataclass(frozen=True)
class Achievement:
    key: str
    name: str
    text: str
    icon: str  # lucide icon name, drawn by the web app
    check: Callable[[Store], bool]


def _n(store: Store, sql: str, params: tuple = ()) -> int:
    row = store.one(sql, params)
    return int(next(iter(row.values()))) if row else 0


def _xp(reason: str, at_least: int = 1) -> Callable[[Store], bool]:
    return lambda s: _n(s, "select count(*) n from xp_events where reason = ?", (reason,)) >= at_least


def _best_streak(s: Store) -> int:
    return streaks([r["local_day"] for r in s.all("select distinct local_day from xp_events")])[1]


def _all_solved(s: Store, difficulty: str | None = None) -> bool:
    from . import arena

    problems = [p for p in arena.list_problems(s) if difficulty is None or p["difficulty"] == difficulty]
    return bool(problems) and all(p["status"] == "solved" for p in problems)


def _numbers_interview(s: Store) -> bool:
    for sess in s.all("select id from interview_sessions where status = 'completed'"):
        turns = s.all("select checks from interview_turns where session_id = ? and question_source != 'technical'", (sess["id"],))
        if turns and all('"mentions_number":true' in t["checks"] for t in turns):
            return True
    return False


ACHIEVEMENTS: list[Achievement] = [
    Achievement(
        "first_hit", "First blood", "Land your first verified correct answer.", "Sword", lambda s: _n(s, "select count(*) n from exam_attempts where correct = 1") >= 1
    ),
    Achievement(
        "first_boss", "Boss slayer", "Defeat a boss.", "Crown", lambda s: _n(s, "select count(*) n from exam_sessions where kind = 'course' and outcome = 'victory'") >= 1
    ),
    Achievement(
        "two_bosses",
        "Double major",
        "Defeat bosses from two different courses.",
        "Swords",
        lambda s: _n(s, "select count(distinct course_id) n from exam_sessions where kind = 'course' and outcome = 'victory'") >= 2,
    ),
    Achievement(
        "flawless",
        "Flawless",
        "Win a boss fight without losing a heart.",
        "Heart",
        lambda s: _n(s, "select count(*) n from exam_sessions where kind = 'course' and outcome = 'victory' and hearts = 5") >= 1,
    ),
    Achievement(
        "no_hints",
        "No training wheels",
        "Win a boss fight without using a hint.",
        "EyeOff",
        lambda s: (
            _n(
                s,
                "select count(*) n from exam_sessions e where e.kind = 'course' and e.outcome = 'victory' "
                "and not exists (select 1 from exam_questions q where q.session_id = e.id and q.hint_used = 1)",
            )
            >= 1
        ),
    ),
    Achievement(
        "combo_10", "Unstoppable", "Get 10 answers right in a row in one fight.", "Zap", lambda s: _n(s, "select coalesce(max(best_combo), 0) n from exam_sessions") >= 10
    ),
    Achievement("comeback", "Comeback", "Get a rematch question right after missing it.", "Repeat", _xp("rematch_redeemed")),
    Achievement("clean_5", "Show-off", "Turn in 5 answers with every line of work correct.", "ListChecks", _xp("clean_work", 5)),
    Achievement("raid_1", "Raider", "Clear a Daily Raid.", "Hourglass", _xp("raid_cleared")),
    Achievement("raid_5", "Nothing fades", "Clear 5 Daily Raids.", "Shield", _xp("raid_cleared", 5)),
    Achievement("party_1", "Party up", "Beat a boss in a party raid.", "Users", _xp("party_cleared")),
    Achievement("streak_3", "Warming up", "Practice 3 days in a row.", "Flame", lambda s: _best_streak(s) >= 3),
    Achievement("streak_7", "Week of reps", "Practice 7 days in a row.", "Flame", lambda s: _best_streak(s) >= 7),
    Achievement(
        "first_solve",
        "Hello, Arena",
        "Solve your first Arena problem.",
        "Code2",
        lambda s: _n(s, "select count(*) n from coding_submissions where is_submit = 1 and verdict = 'accepted'") >= 1,
    ),
    Achievement("speed_tier", "Big-O energy", "Clear a speed tier with an efficient solution.", "Gauge", _xp("coding_fast")),
    Achievement("arena_easy", "Fundamentals", "Solve every easy Arena problem.", "CheckCheck", lambda s: _all_solved(s, "easy")),
    Achievement("arena_all", "Arena champion", "Solve every Arena problem.", "Trophy", lambda s: _all_solved(s)),
    Achievement(
        "first_interview",
        "Opening statement",
        "Finish a mock interview.",
        "Mic",
        lambda s: _n(s, "select count(*) n from interview_sessions where status = 'completed'") >= 1,
    ),
    Achievement("numbers_talk", "Numbers talk", "Finish an interview where every answer includes a number.", "Hash", _numbers_interview),
    Achievement("level_5", "Level 5", "Reach level 5.", "Star", lambda s: level_for(_n(s, "select coalesce(sum(amount), 0) n from xp_events")).level >= 5),
]
_BY_KEY = {a.key: a for a in ACHIEVEMENTS}


def check(store: Store) -> list[str]:
    """Unlock anything newly earned. Returns the keys unlocked by this call."""
    have = {r["key"] for r in store.all("select key from achievements")}
    new = []
    for a in ACHIEVEMENTS:
        if a.key in have:
            continue
        try:
            earned = a.check(store)
        except Exception:  # a broken check must never break the hub
            earned = False
        if earned:
            inserted = store.run("insert or ignore into achievements (key, unlocked_at, seen) values (?, ?, 0)", (a.key, now_iso()))
            if inserted:
                award(store, "achievement", ACHIEVEMENT_XP, "achievement", a.key)
                new.append(a.key)
    return new


def listing(store: Store) -> list[dict[str, Any]]:
    unlocked = {r["key"]: r for r in store.all("select key, unlocked_at from achievements")}
    return [
        {"key": a.key, "name": a.name, "text": a.text, "icon": a.icon, "xp": ACHIEVEMENT_XP, "unlocked_at": unlocked[a.key]["unlocked_at"] if a.key in unlocked else None}
        for a in ACHIEVEMENTS
    ]


def unseen(store: Store) -> list[dict[str, Any]]:
    rows = store.all("select key from achievements where seen = 0 order by unlocked_at")
    return [{"key": r["key"], "name": _BY_KEY[r["key"]].name, "text": _BY_KEY[r["key"]].text, "icon": _BY_KEY[r["key"]].icon} for r in rows if r["key"] in _BY_KEY]


def mark_seen(store: Store, keys: list[str]) -> None:
    for k in keys:
        store.run("update achievements set seen = 1 where key = ?", (k,))
