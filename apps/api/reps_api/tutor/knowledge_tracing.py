"""Bayesian Knowledge Tracing (Corbett & Anderson, 1995) and the boss policy built on it.

Per topic, BKT tracks P(known). After each graded attempt:

    posterior = P(known | observation)          (Bayes rule with slip and guess)
    P(known)' = posterior + (1 - posterior) * P(learn)

The default parameters below are reasonable starting values, not fitted ones.
eval/assistments_bkt.py fits them on real data once the dataset is available.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

MODEL_VERSION = "bkt-1.0"
MIN_EVIDENCE = 3  # attempts before an estimate stops being "provisional"


@dataclass(frozen=True)
class BKTParams:
    p_init: float = 0.30  # P(known) before any attempt
    p_learn: float = 0.15  # P(unknown -> known) after an attempt
    p_slip: float = 0.10  # P(wrong | known)
    p_guess: float = 0.20  # P(right | unknown); 0.25 fits 4-option multiple choice

    def __post_init__(self) -> None:
        for name in ("p_init", "p_learn", "p_slip", "p_guess"):
            v = getattr(self, name)
            if not 0.0 < v < 1.0:
                raise ValueError(f"{name} must be strictly between 0 and 1, got {v}")
        if self.p_slip + self.p_guess >= 1.0:
            raise ValueError("p_slip + p_guess must be < 1, or a correct answer stops being evidence of knowing")


DEFAULT_PARAMS = BKTParams()


def posterior(p_known: float, correct: bool, params: BKTParams = DEFAULT_PARAMS) -> float:
    s, g = params.p_slip, params.p_guess
    if correct:
        num = p_known * (1 - s)
        den = num + (1 - p_known) * g
    else:
        num = p_known * s
        den = num + (1 - p_known) * (1 - g)
    return num / den


def update(p_known: float, correct: bool, params: BKTParams = DEFAULT_PARAMS) -> float:
    if not 0.0 <= p_known <= 1.0:
        raise ValueError("p_known must be a probability")
    post = posterior(p_known, correct, params)
    return post + (1 - post) * params.p_learn


def predict_correct(p_known: float, params: BKTParams = DEFAULT_PARAMS) -> float:
    return p_known * (1 - params.p_slip) + (1 - p_known) * params.p_guess


@dataclass(frozen=True)
class TopicMastery:
    topic_id: str
    p_known: float
    attempts: int = 0
    correct: int = 0

    @property
    def provisional(self) -> bool:
        return self.attempts < MIN_EVIDENCE

    def record(self, correct: bool, params: BKTParams = DEFAULT_PARAMS) -> TopicMastery:
        return replace(
            self,
            p_known=update(self.p_known, correct, params),
            attempts=self.attempts + 1,
            correct=self.correct + int(correct),
        )


def fresh(topic_id: str, params: BKTParams = DEFAULT_PARAMS) -> TopicMastery:
    return TopicMastery(topic_id=topic_id, p_known=params.p_init)


# ----------------------------------------------------------------- boss policy


def boss_hp(topics: Sequence[TopicMastery]) -> int:
    """Boss HP = 100 x (1 - average P(known)) across the exam's topics.

    HP falls when mastery rises and can climb back after mistakes. It's an
    interpretable readiness gauge, not a probability of passing the exam.
    """
    if not topics:
        return 100
    mean = sum(t.p_known for t in topics) / len(topics)
    return round(100 * (1 - mean))


@dataclass
class BossPolicy:
    """Choose which topic the boss attacks next.

    1. Coverage first: every topic gets asked once before any repeats.
    2. Exploration: with probability `explore`, pick a random topic not asked
       in the last `cooldown` questions.
    3. Otherwise exploit: the lowest P(known) topic, skipping a topic that
       has been asked `max_streak` times in a row so one weakness can't
       take over the whole fight.
    """

    explore: float = 0.15
    cooldown: int = 2
    max_streak: int = 2
    rng: random.Random = field(default_factory=random.Random)

    def next_topic(self, topics: Sequence[TopicMastery], recent: Sequence[str]) -> str:
        if not topics:
            raise ValueError("boss has no topics")
        ids = [t.topic_id for t in topics]
        untouched = [t.topic_id for t in topics if t.attempts == 0 and t.topic_id not in recent]
        if untouched:
            return untouched[0]

        cooling = set(recent[-self.cooldown :]) if self.cooldown else set()
        if len(ids) > 1 and self.rng.random() < self.explore:
            pool = [i for i in ids if i not in cooling] or ids
            return self.rng.choice(pool)

        streak_blocked: set[str] = set()
        if len(recent) >= self.max_streak and len(set(recent[-self.max_streak :])) == 1:
            streak_blocked = {recent[-1]}
        candidates = [t for t in topics if t.topic_id not in streak_blocked] or list(topics)
        return min(candidates, key=lambda t: (t.p_known, t.attempts)).topic_id


# ----------------------------------------------------------------- forgetting
#
# Standard BKT never forgets. Reps adds a documented, tunable extension: above the
# prior, mastery decays exponentially toward the prior while a topic goes
# unpractised. Each correct answer slows the decay (spacing effect), so a topic
# you've nailed many times fades over weeks, one you got right once fades in days.
# These constants are design choices, not fitted values.

BASE_HALF_LIFE_DAYS = 3.0
HALF_LIFE_GROWTH = 1.6  # per correct answer, capped below
MAX_GROWTH_STEPS = 6
FORGETTING_VERSION = "decay-1.0"


def half_life_days(correct: int) -> float:
    return BASE_HALF_LIFE_DAYS * HALF_LIFE_GROWTH ** min(max(correct, 0), MAX_GROWTH_STEPS)


def decayed(p_known: float, days_since: float, correct: int, params: BKTParams = DEFAULT_PARAMS) -> float:
    """Mastery after `days_since` days without practice. Never drops below the prior,
    and never raises a below-prior estimate (forgetting can't make you better)."""
    if days_since <= 0 or p_known <= params.p_init:
        return p_known
    return params.p_init + (p_known - params.p_init) * 0.5 ** (days_since / half_life_days(correct))
