import pytest
import sympy as sp

from reps_api.verification import math_engine
from reps_api.verification.math_engine import (
    MathProblemSpec,
    MathTask,
    ParamSpec,
    grade_answer,
    instantiate,
    verify_problem,
)
from reps_api.verification.safe_math import UnsupportedExpression, parse_math
from reps_api.verification.status import InvalidTransition, VerificationStatus, is_publishable, transition

V = VerificationStatus


# ------------------------------------------------------------------ safe parsing


@pytest.mark.parametrize(
    "text, expected",
    [
        ("3x^2 + 2*sin(x)", "3*x**2 + 2*sin(x)"),
        ("2(x+1)", "2*x + 2"),
        ("e^x", "exp(x)"),
        ("ln(x)", "log(x)"),
        ("x^2 - 4 = 0", "x**2 - 4"),
    ],
)
def test_parses_common_notation(text, expected):
    assert parse_math(text) == sp.sympify(expected, locals={"x": sp.Symbol("x", real=True)})


@pytest.mark.parametrize(
    "text",
    [
        '__import__("os")',
        "x.__class__",
        "lambda: 1",
        "open(x)",
        "9**9**9",
        "2**500",
        "1/0",
        "x = 1 = 2",
        "",
        "x" * 400,
        "[x]",
    ],
)
def test_rejects_unsafe_or_unsupported(text):
    with pytest.raises(UnsupportedExpression):
        parse_math(text)


# ------------------------------------------------------------------ state machine


def test_status_transitions():
    assert transition(V.PENDING, V.VERIFIED) is V.VERIFIED
    for terminal in (V.VERIFIED, V.REJECTED, V.UNSUPPORTED, V.AI_EVALUATED):
        with pytest.raises(InvalidTransition):
            transition(terminal, V.VERIFIED if terminal is not V.VERIFIED else V.REJECTED)
    assert is_publishable(V.VERIFIED) and is_publishable(V.AI_EVALUATED)
    assert not is_publishable(V.PENDING) and not is_publishable(V.REJECTED)


# ------------------------------------------------------------------ verification


def spec(kind, expr, claimed=None, params=None, **task):
    return MathProblemSpec(
        statement="s",
        params={k: ParamSpec(min=lo, max=hi) for k, (lo, hi) in (params or {}).items()},
        task=MathTask(kind=kind, expr=expr, **task),
        claimed_answer=claimed,
    )


@pytest.mark.parametrize(
    "problem",
    [
        spec("derivative", "{a}*x^{n} + sin(x)", "{a}*{n}*x^({n}-1) + cos(x)", {"a": (2, 9), "n": (2, 5)}),
        spec("derivative_at", "x*ln(x)", at="2"),
        spec("integral_definite", "x*exp(x)", "1", lower="0", upper="1"),
        spec("integral_indefinite", "x*cos(x)", "x*sin(x) + cos(x) + 5"),
        spec("solve", "(x-{r})*(x+{s})", "{r}, -{s}", {"r": (1, 5), "s": (1, 5)}),
        spec("solve", "x^2 - 6x + 9", "3"),
        spec("limit", "sin(x)/x", "1", at="0"),
        spec("limit", "(3x^2+1)/(x^2-5)", "3", at="oo"),
        spec("evaluate", "sqrt(8)*sqrt(2) + 3^2", "13"),
    ],
)
def test_correct_problems_verify(problem):
    for seed in range(3):
        result = verify_problem(problem, seed)
        assert result.status is V.VERIFIED, result.reason
        assert result.answer is not None
        assert all(c.passed for c in result.checks)
        assert len(result.checks) >= 2  # symbolic + independent numeric


def test_wrong_claimed_key_is_rejected():
    result = verify_problem(spec("derivative", "{a}*x^3", "{a}*x^2", {"a": (2, 9)}), seed=1)
    assert result.status is V.REJECTED
    assert "claimed" in result.reason
    assert result.answer is None


def test_wrong_root_count_is_rejected():
    result = verify_problem(spec("solve", "x^2 - 9", "3"), seed=0)
    assert result.status is V.REJECTED


def test_numeric_check_catches_a_wrong_symbolic_answer(monkeypatch):
    """If SymPy (or a future bug) produced a wrong key, the numeric path must catch it."""
    real = math_engine._symbolic

    def broken(task):
        return real(task) + 1

    monkeypatch.setattr(math_engine, "_symbolic", broken)
    for problem in (
        spec("derivative", "x^3"),
        spec("integral_definite", "x^2", lower="0", upper="3"),
        spec("derivative_at", "x^3", at="2"),
        spec("limit", "sin(x)/x", at="0"),
    ):
        result = verify_problem(problem, seed=0)
        assert result.status is V.REJECTED, problem.task.kind


def test_numeric_root_scan_catches_a_missing_root(monkeypatch):
    monkeypatch.setattr(math_engine, "_symbolic", lambda task: sp.FiniteSet(2))
    assert verify_problem(spec("solve", "(x-2)*(x+7)"), seed=0).status is V.REJECTED


@pytest.mark.parametrize(
    "problem",
    [
        spec("solve", "sin(x)"),  # infinitely many roots
        spec("integral_indefinite", "exp(x^2)*sin(x^3)"),  # no closed form
        spec("derivative", "{zz}*x", params={"a": (1, 2)}),  # undeclared parameter
        spec("evaluate", "x + 1"),  # free variable
    ],
)
def test_unsupported_problems_never_verify(problem):
    result = verify_problem(problem, seed=0)
    assert result.status in (V.UNSUPPORTED, V.REJECTED)


def test_no_real_solutions_rejected():
    assert verify_problem(spec("solve", "x^2 + 1"), seed=0).status is V.REJECTED


def test_instances_are_reproducible_and_vary():
    p = spec("derivative", "{a}*x^{n}", params={"a": (1, 50), "n": (2, 9)})
    assert instantiate(p, 5) == instantiate(p, 5)
    assert len({tuple(instantiate(p, s).values.items()) for s in range(20)}) > 5


# ------------------------------------------------------------------ grading


def task(kind, expr, **kw):
    return MathTask(kind=kind, expr=expr, **kw)


@pytest.mark.parametrize(
    "t, key, answer, correct",
    [
        (task("derivative", "x^2*sin(x)"), "2*x*sin(x) + x**2*cos(x)", "x(2sin(x) + x cos(x))", True),
        (task("derivative", "x^2*sin(x)"), "2*x*sin(x) + x**2*cos(x)", "2x cos(x)", False),
        (task("integral_indefinite", "x*cos(x)"), "x*sin(x) + cos(x)", "x sin(x) + cos(x) + 42", True),
        (task("integral_indefinite", "x*cos(x)"), "x*sin(x) + cos(x)", "x sin(x) - cos(x)", False),
        (task("integral_definite", "x^2", lower="0", upper="3"), "9", "18/2", True),
        (task("integral_definite", "x^2", lower="0", upper="3"), "9", "9.0000000001", True),
        (task("integral_definite", "x^2", lower="0", upper="3"), "9", "8.9", False),
        (task("solve", "x^2-1"), "-1, 1", "x = 1 or x = -1", True),
        (task("solve", "x^2-1"), "-1, 1", "1", False),
        (task("limit", "(3x^2+1)/(x^2-5)", at="oo"), "3", "3", True),
        (task("evaluate", "sqrt(2)/2"), "sqrt(2)/2", "1/sqrt(2)", True),
        (task("derivative", "x^3"), "3*x**2", "3y^2", None),  # unknown variable: flagged, not marked
    ],
)
def test_grading_accepts_equivalent_forms(t, key, answer, correct):
    result = grade_answer(t, key, answer)
    assert result.correct is correct, result


def test_grading_unparseable_is_not_marked_wrong_or_right():
    result = grade_answer(task("derivative", "x^3"), "3*x**2", "import os")
    assert result.correct is None and result.status == "unparseable"
