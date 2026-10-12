"""Verification status values and the only legal transitions between them.

A question is born `pending`. Exactly one of the verification paths moves it to a
terminal state. Nothing moves a question out of a terminal state: regenerating a
rejected problem creates a new question version instead of reviving the old one.
"""

from enum import Enum


class VerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"  # deterministic checks agreed
    AI_EVALUATED = "ai_evaluated"  # conceptual; graded by rubric, not proven
    REJECTED = "rejected"  # checks disagreed or failed
    UNSUPPORTED = "unsupported"  # outside what the engine can check


_ALLOWED: dict[VerificationStatus, frozenset[VerificationStatus]] = {
    VerificationStatus.PENDING: frozenset(
        {
            VerificationStatus.VERIFIED,
            VerificationStatus.AI_EVALUATED,
            VerificationStatus.REJECTED,
            VerificationStatus.UNSUPPORTED,
        }
    ),
    VerificationStatus.VERIFIED: frozenset(),
    VerificationStatus.AI_EVALUATED: frozenset(),
    VerificationStatus.REJECTED: frozenset(),
    VerificationStatus.UNSUPPORTED: frozenset(),
}

PUBLISHABLE = frozenset({VerificationStatus.VERIFIED, VerificationStatus.AI_EVALUATED})


class InvalidTransition(ValueError):
    pass


def transition(current: VerificationStatus, new: VerificationStatus) -> VerificationStatus:
    if new not in _ALLOWED[current]:
        raise InvalidTransition(f"cannot move verification status from {current.value} to {new.value}")
    return new


def is_publishable(status: VerificationStatus) -> bool:
    return status in PUBLISHABLE
