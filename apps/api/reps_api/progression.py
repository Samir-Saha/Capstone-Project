"""XP, levels and streaks. All reward rules live here.

XP is motivation, not evidence of knowledge: mastery comes only from the knowledge
tracing model. Every award is tied to one confirmed event (a graded attempt, an
accepted submission, a finished session) and the database refuses a second award
for the same event, so retries and refreshes can't farm XP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .store import Store, local_day, new_id, now_iso

# reason -> base amount
XP_RULES: dict[str, int] = {
    "exam_correct": 10,  # + combo bonus, see exam_correct_xp
    "boss_defeated": 50,
    "exam_session_finished": 15,
    "coding_accepted_easy": 25,
    "coding_accepted_medium": 40,
    "coding_accepted_hard": 60,
    "coding_fast": 15,  # passed the speed tier
    "rematch_redeemed": 5,  # got right a question you'd missed earlier
    "clean_work": 5,  # show-your-work with every checked line correct
    "raid_cleared": 40,  # once per day
    "interview_answer": 10,
    "interview_finished": 30,
}


def exam_correct_xp(combo: int, hint_used: bool) -> int:
    """10 XP, +5 for every 3-answer streak in the current fight (max +15), halved with a hint."""
    bonus = min(15, 5 * (combo // 3))
    amount = XP_RULES["exam_correct"] + bonus
    return max(1, amount // 2) if hint_used else amount


def award(store: Store, reason: str, amount: int, source_type: str, source_id: str) -> int:
    """Returns XP actually granted: 0 if this event was already rewarded."""
    if amount <= 0:
        return 0
    inserted = store.run(
        "insert or ignore into xp_events (id, reason, amount, source_type, source_id, created_at, local_day) values (?, ?, ?, ?, ?, ?, ?)",
        (new_id(), reason, amount, source_type, source_id, now_iso(), local_day()),
    )
    return amount if inserted else 0


def xp_to_next(level: int) -> int:
    """XP needed to go from `level` to `level + 1`: 100, 150, 200, ..."""
    return 100 + 50 * (level - 1)


@dataclass(frozen=True)
class Level:
    level: int
    total_xp: int
    into_level: int
    needed: int


def level_for(total_xp: int) -> Level:
    level, remaining = 1, total_xp
    while remaining >= xp_to_next(level):
        remaining -= xp_to_next(level)
        level += 1
    return Level(level=level, total_xp=total_xp, into_level=remaining, needed=xp_to_next(level))


def streaks(days: list[str], today: str | None = None) -> tuple[int, int]:
    """(current, best) runs of consecutive practice days.

    The current streak stays alive through today: practicing yesterday but not yet
    today still counts, so the streak never "breaks" in the morning.
    """
    if not days:
        return 0, 0
    parsed = sorted({date.fromisoformat(d) for d in days})
    best = run = 1
    for prev, cur in zip(parsed, parsed[1:]):
        run = run + 1 if cur - prev == timedelta(days=1) else 1
        best = max(best, run)
    t = date.fromisoformat(today or local_day())
    last = parsed[-1]
    if t - last > timedelta(days=1):
        return 0, best
    current = 1
    for i in range(len(parsed) - 1, 0, -1):
        if parsed[i] - parsed[i - 1] == timedelta(days=1):
            current += 1
        else:
            break
    return current, best
