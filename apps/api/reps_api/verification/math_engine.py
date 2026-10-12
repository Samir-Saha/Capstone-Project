"""Answer-key verification and student grading for computational math problems.

A generated problem is a *template* plus a declarative *task*, never runnable code.
For each instance the engine computes the answer twice by unrelated methods:

    1. symbolic: SymPy (diff, integrate, solveset, limit, simplify)
    2. numeric:  mpmath at 30 digits (numerical differentiation, quadrature,
                 root scanning, approach-the-point limits)

If the generator also supplied its own claimed answer, that becomes a third check.
The problem is published only if every check agrees. Any disagreement, error, or
unsupported construct rejects it, and the reason is recorded.
"""

from __future__ import annotations

import random
import re
import time
from typing import Literal

import mpmath
import sympy as sp
from pydantic import BaseModel, Field, field_validator

from .safe_math import UnsupportedExpression, parse_math, symbol
from .status import VerificationStatus

mpmath.mp.dps = 30

TaskKind = Literal[
    "evaluate",
    "derivative",
    "derivative_at",
    "integral_definite",
    "integral_indefinite",
    "solve",
    "limit",
]

REL_TOL = 1e-7
ABS_TOL = 1e-9
ROOT_WINDOW = 100.0  # numeric root scan covers [-ROOT_WINDOW, ROOT_WINDOW]


# --------------------------------------------------------------------------- specs


class ParamSpec(BaseModel):
    min: int
    max: int
    exclude: list[int] = Field(default_factory=list)

    @field_validator("max")
    @classmethod
    def _range(cls, v: int, info) -> int:
        lo = info.data.get("min")
        if lo is not None and v < lo:
            raise ValueError("max must be >= min")
        if abs(v) > 10_000:
            raise ValueError("parameter bound too large")
        return v


class MathTask(BaseModel):
    kind: TaskKind
    expr: str
    var: str = "x"
    at: str | None = None  # derivative_at, limit
    lower: str | None = None  # integral_definite
    upper: str | None = None
    order: int = Field(default=1, ge=1, le=4)


class MathProblemSpec(BaseModel):
    """What the question generator must return for a computational problem."""

    statement: str
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    task: MathTask
    claimed_answer: str | None = None  # generator's own key, same {param} placeholders

    @field_validator("params")
    @classmethod
    def _param_names(cls, v: dict[str, ParamSpec]) -> dict[str, ParamSpec]:
        for name in v:
            if not re.fullmatch(r"[a-z][a-z0-9]{0,7}", name):
                raise ValueError(f"bad parameter name '{name}'")
        return v


class MathInstance(BaseModel):
    seed: int
    values: dict[str, int]
    statement: str
    task: MathTask
    claimed_answer: str | None


class CheckRecord(BaseModel):
    method: str
    passed: bool
    detail: str = ""


class MathVerification(BaseModel):
    status: VerificationStatus
    instance: MathInstance | None = None
    answer: str | None = None  # canonical key, stored server-side only
    answer_latex: str | None = None
    checks: list[CheckRecord] = Field(default_factory=list)
    reason: str | None = None
    duration_ms: int = 0


class GradeResult(BaseModel):
    correct: bool | None  # None = could not grade
    status: Literal["correct", "incorrect", "unparseable"]
    method: str
    detail: str = ""


# ---------------------------------------------------------------- instantiation


def _fill(template: str | None, values: dict[str, int], wrap: bool) -> str | None:
    if template is None:
        return None

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in values:
            raise UnsupportedExpression(f"template uses undeclared parameter '{name}'")
        return f"({values[name]})" if wrap else str(values[name])

    return re.sub(r"\{([a-z][a-z0-9]{0,7})\}", sub, template)


def instantiate(spec: MathProblemSpec, seed: int) -> MathInstance:
    rng = random.Random(seed)
    values: dict[str, int] = {}
    for name, p in sorted(spec.params.items()):
        choices = [v for v in range(p.min, p.max + 1) if v not in p.exclude]
        if not choices:
            raise UnsupportedExpression(f"parameter '{name}' has no allowed values")
        values[name] = rng.choice(choices)
    t = spec.task
    task = MathTask(
        kind=t.kind,
        expr=_fill(t.expr, values, wrap=True) or "",
        var=t.var,
        at=_fill(t.at, values, wrap=True),
        lower=_fill(t.lower, values, wrap=True),
        upper=_fill(t.upper, values, wrap=True),
        order=t.order,
    )
    return MathInstance(
        seed=seed,
        values=values,
        statement=_fill(spec.statement, values, wrap=False) or "",
        task=task,
        claimed_answer=_fill(spec.claimed_answer, values, wrap=True),
    )


# ------------------------------------------------------------------- helpers


def _vars(task: MathTask) -> tuple[str, ...]:
    if not re.fullmatch(r"[a-z]", task.var):
        raise UnsupportedExpression("variable must be a single lowercase letter")
    return (task.var,)


def _num(expr: sp.Expr) -> mpmath.mpf | mpmath.mpc:
    value = sp.N(expr, 30)
    if value.has(sp.zoo, sp.nan) or not value.is_number:
        raise UnsupportedExpression("value is not a finite number")
    return mpmath.mpmathify(complex(value)) if not value.is_real else mpmath.mpf(str(value))


def _close(a, b) -> bool:
    if a in (mpmath.inf, -mpmath.inf) or b in (mpmath.inf, -mpmath.inf):
        return a == b
    return abs(a - b) <= max(ABS_TOL, REL_TOL * max(abs(a), abs(b)))


def _fn(expr: sp.Expr, var: sp.Symbol):
    return sp.lambdify(var, expr, modules="mpmath")


def _sample_points(rng: random.Random, n: int = 6) -> list[mpmath.mpf]:
    return [mpmath.mpf(rng.uniform(0.3, 2.7)) * rng.choice([1, -1]) for _ in range(n)]


def _real_finite(values) -> bool:
    try:
        return all(mpmath.isfinite(v) and abs(mpmath.im(v)) < 1e-12 for v in values)
    except (TypeError, ValueError):
        return False


def _same_function(f, g, var: sp.Symbol, rng: random.Random, up_to_constant: bool = False) -> tuple[bool, str]:
    """Numerically compare two expressions at random points where both are defined."""
    fl, gl = _fn(f, var), _fn(g, var)
    diffs = []
    for pt in _sample_points(rng, 12):
        try:
            a, b = fl(pt), gl(pt)
        except (ZeroDivisionError, ValueError, TypeError, OverflowError):
            continue
        if not _real_finite([a, b]):
            continue
        diffs.append((a, b))
        if len(diffs) >= 6:
            break
    if len(diffs) < 3:
        return False, "too few points where both expressions are defined"
    if up_to_constant:
        offset = diffs[0][0] - diffs[0][1]
        ok = all(_close(a - b, offset) for a, b in diffs)
    else:
        ok = all(_close(a, b) for a, b in diffs)
    return ok, f"compared at {len(diffs)} points"


# ------------------------------------------------------------- symbolic path


def _symbolic(task: MathTask) -> sp.Expr | sp.FiniteSet:
    v = _vars(task)
    x = symbol(task.var)
    f = parse_math(task.expr, v)
    if task.kind == "evaluate":
        if f.free_symbols:
            raise UnsupportedExpression("evaluate task still has free variables")
        return sp.nsimplify(sp.simplify(f), rational=False)
    if task.kind == "derivative":
        return sp.simplify(sp.diff(f, x, task.order))
    if task.kind == "derivative_at":
        if task.at is None:
            raise UnsupportedExpression("derivative_at needs 'at'")
        return sp.simplify(sp.diff(f, x, task.order).subs(x, parse_math(task.at, ())))
    if task.kind == "integral_definite":
        if task.lower is None or task.upper is None:
            raise UnsupportedExpression("definite integral needs bounds")
        result = sp.integrate(f, (x, parse_math(task.lower, ()), parse_math(task.upper, ())))
        if result.has(sp.Integral):
            raise UnsupportedExpression("SymPy could not evaluate the integral")
        return sp.simplify(result)
    if task.kind == "integral_indefinite":
        result = sp.integrate(f, x)
        if result.has(sp.Integral):
            raise UnsupportedExpression("SymPy could not find an antiderivative")
        return sp.simplify(result)
    if task.kind == "solve":
        roots = sp.solveset(f, x, domain=sp.S.Reals)
        if roots is sp.S.EmptySet:
            return sp.FiniteSet()
        if not isinstance(roots, sp.FiniteSet):
            raise UnsupportedExpression("solution set is not a finite set of reals")
        if any(abs(float(r)) > ROOT_WINDOW for r in roots):
            raise UnsupportedExpression("root outside the numeric check window")
        return roots
    if task.kind == "limit":
        if task.at is None:
            raise UnsupportedExpression("limit needs 'at'")
        return sp.limit(f, x, parse_math(task.at, ()))
    raise UnsupportedExpression(f"unknown task kind {task.kind}")


# -------------------------------------------------------------- numeric path


def _numeric_roots(f_l, rng: random.Random) -> list[mpmath.mpf]:
    found: list[mpmath.mpf] = []

    def add(r):
        if not any(abs(r - s) < 1e-6 for s in found):
            found.append(r)

    grid = [mpmath.mpf(-ROOT_WINDOW) + i * mpmath.mpf(2 * ROOT_WINDOW) / 4000 for i in range(4001)]
    prev_x, prev_y = None, None
    for gx in grid:
        try:
            gy = f_l(gx)
            if not _real_finite([gy]):
                prev_x, prev_y = None, None
                continue
            gy = mpmath.re(gy)
        except (ZeroDivisionError, ValueError, TypeError, OverflowError):
            prev_x, prev_y = None, None
            continue
        if gy == 0:
            add(gx)
        elif prev_y is not None and prev_y * gy < 0:
            try:
                r = mpmath.findroot(f_l, (prev_x, gx), solver="anderson")
                if abs(f_l(r)) < 1e-12:
                    add(mpmath.re(r))
            except (ValueError, ZeroDivisionError):
                pass
        prev_x, prev_y = gx, gy
    # Even-multiplicity roots don't change sign; polish local minima of |f|.
    for start in [rng.uniform(-ROOT_WINDOW, ROOT_WINDOW) for _ in range(40)] + list(range(-10, 11)):
        try:
            r = mpmath.findroot(f_l, mpmath.mpf(start), solver="newton", tol=1e-25, maxsteps=200)
            if mpmath.im(r) == 0 and abs(mpmath.re(r)) <= ROOT_WINDOW and abs(f_l(mpmath.re(r))) < 1e-15:
                add(mpmath.re(r))
        except (ValueError, ZeroDivisionError, TypeError):
            pass
    return sorted(found)


def _numeric_check(task: MathTask, symbolic, rng: random.Random) -> CheckRecord:
    v = _vars(task)
    x = symbol(task.var)
    f = parse_math(task.expr, v)
    fl = _fn(f, x)

    if task.kind == "evaluate":
        direct = mpmath.mpmathify(complex(sp.lambdify((), f, modules="math")()))
        ok = _close(direct, _num(symbolic))
        return CheckRecord(method="float re-evaluation", passed=ok, detail=f"{mpmath.nstr(direct, 12)}")

    if task.kind == "derivative":
        sl = _fn(symbolic, x)
        pts = 0
        for pt in _sample_points(rng, 12):
            try:
                expected = mpmath.diff(fl, pt, task.order)
                got = sl(pt)
            except (ZeroDivisionError, ValueError, TypeError):
                continue
            if not _real_finite([expected, got]):
                continue
            if not _close(expected, got):
                return CheckRecord(method="numerical differentiation", passed=False, detail=f"disagree at x={mpmath.nstr(pt, 6)}")
            pts += 1
            if pts >= 6:
                break
        return CheckRecord(method="numerical differentiation", passed=pts >= 3, detail=f"agreed at {pts} points")

    if task.kind == "derivative_at":
        at = _num(parse_math(task.at or "", ()))
        expected = mpmath.diff(fl, at, task.order)
        return CheckRecord(method="numerical differentiation", passed=_close(expected, _num(symbolic)), detail=mpmath.nstr(expected, 12))

    if task.kind == "integral_definite":
        lo, hi = _num(parse_math(task.lower or "", ())), _num(parse_math(task.upper or "", ()))
        expected = mpmath.quad(fl, [lo, hi])
        return CheckRecord(method="numerical quadrature", passed=_close(expected, _num(symbolic)), detail=mpmath.nstr(expected, 12))

    if task.kind == "integral_indefinite":
        F = _fn(symbolic, x)
        checks = 0
        for _ in range(12):
            a, b = sorted([mpmath.mpf(rng.uniform(0.2, 2.5)), mpmath.mpf(rng.uniform(0.2, 2.5))])
            if b - a < 0.1:
                continue
            try:
                area = mpmath.quad(fl, [a, b])
                delta = F(b) - F(a)
            except (ZeroDivisionError, ValueError, TypeError):
                continue
            if not _real_finite([area, delta]):
                continue
            if not _close(area, delta):
                return CheckRecord(method="quadrature vs F(b)-F(a)", passed=False, detail=f"disagree on [{mpmath.nstr(a, 4)}, {mpmath.nstr(b, 4)}]")
            checks += 1
            if checks >= 4:
                break
        return CheckRecord(method="quadrature vs F(b)-F(a)", passed=checks >= 2, detail=f"agreed on {checks} intervals")

    if task.kind == "solve":
        numeric = _numeric_roots(fl, rng)
        symbolic_vals = sorted(_num(r) for r in symbolic)
        ok = len(numeric) == len(symbolic_vals) and all(_close(a, b) for a, b in zip(numeric, symbolic_vals))
        return CheckRecord(
            method="numeric root scan",
            passed=ok,
            detail=f"numeric roots {[mpmath.nstr(r, 8) for r in numeric]}",
        )

    if task.kind == "limit":
        at_expr = parse_math(task.at or "", ())
        if at_expr in (sp.oo, -sp.oo):
            sign = 1 if at_expr == sp.oo else -1
            seq = [fl(sign * mpmath.mpf(10) ** k) for k in (6, 8, 10, 12)]
        else:
            a = _num(at_expr)
            seq = []
            for k in (6, 8, 10, 12):
                h = mpmath.mpf(10) ** (-k)
                seq.append((fl(a + h) + fl(a - h)) / 2)
            left = fl(a - mpmath.mpf(10) ** -12)
            right = fl(a + mpmath.mpf(10) ** -12)
            if not _close(left, right):
                return CheckRecord(method="approach the point", passed=False, detail="left and right limits differ")
        if symbolic in (sp.oo, -sp.oo):
            grows = all(abs(s) > 1e5 for s in seq[-2:]) and mpmath.sign(seq[-1]) == (1 if symbolic == sp.oo else -1)
            return CheckRecord(method="approach the point", passed=grows, detail="diverges" if grows else "did not diverge")
        target = _num(symbolic)
        ok = abs(seq[-1] - target) <= max(1e-6, 1e-6 * abs(target))
        return CheckRecord(method="approach the point", passed=ok, detail=mpmath.nstr(seq[-1], 10))

    raise UnsupportedExpression(f"no numeric method for {task.kind}")


def _claimed_check(task: MathTask, claimed: str, symbolic, rng: random.Random) -> CheckRecord:
    x = symbol(task.var)
    if task.kind == "solve":
        parts = [p for p in re.split(r"[,;]", claimed) if p.strip()]
        try:
            vals = sorted(_num(parse_math(p, ())) for p in parts)
        except UnsupportedExpression as err:
            return CheckRecord(method="generator's claimed key", passed=False, detail=str(err))
        expected = sorted(_num(r) for r in symbolic)
        ok = len(vals) == len(expected) and all(_close(a, b) for a, b in zip(vals, expected))
        return CheckRecord(method="generator's claimed key", passed=ok)
    try:
        c = parse_math(claimed, _vars(task))
    except UnsupportedExpression as err:
        return CheckRecord(method="generator's claimed key", passed=False, detail=str(err))
    if task.kind in ("derivative", "integral_indefinite"):
        if sp.simplify(c - symbolic) == 0 or (task.kind == "integral_indefinite" and sp.simplify(sp.diff(c - symbolic, x)) == 0):
            return CheckRecord(method="generator's claimed key", passed=True, detail="symbolically equal")
        ok, detail = _same_function(c, symbolic, x, rng, up_to_constant=task.kind == "integral_indefinite")
        return CheckRecord(method="generator's claimed key", passed=ok, detail=detail)
    if symbolic in (sp.oo, -sp.oo) or c in (sp.oo, -sp.oo):
        return CheckRecord(method="generator's claimed key", passed=c == symbolic)
    return CheckRecord(method="generator's claimed key", passed=_close(_num(c), _num(symbolic)))


# ------------------------------------------------------------------- public API


def _answer_to_str(symbolic) -> str:
    if isinstance(symbolic, sp.FiniteSet):
        return ", ".join(str(r) for r in sorted(symbolic, key=lambda r: float(r)))
    return str(symbolic)


def _answer_to_latex(symbolic) -> str:
    if isinstance(symbolic, sp.FiniteSet):
        return ", ".join(sp.latex(r) for r in sorted(symbolic, key=lambda r: float(r)))
    return sp.latex(symbolic)


def verify_instance(instance: MathInstance) -> MathVerification:
    started = time.perf_counter()
    rng = random.Random(instance.seed * 7919 + 17)
    checks: list[CheckRecord] = []

    def done(status: VerificationStatus, reason: str | None = None, answer=None) -> MathVerification:
        return MathVerification(
            status=status,
            instance=instance,
            answer=_answer_to_str(answer) if answer is not None else None,
            answer_latex=_answer_to_latex(answer) if answer is not None else None,
            checks=checks,
            reason=reason,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    try:
        symbolic = _symbolic(instance.task)
    except UnsupportedExpression as err:
        return done(VerificationStatus.UNSUPPORTED, reason=str(err))
    except (NotImplementedError, ValueError, TypeError) as err:
        return done(VerificationStatus.UNSUPPORTED, reason=f"symbolic solver failed: {err.__class__.__name__}")
    checks.append(CheckRecord(method="symbolic (SymPy)", passed=True, detail=_answer_to_str(symbolic)))

    if isinstance(symbolic, sp.Set) and symbolic.is_empty:
        return done(VerificationStatus.REJECTED, reason="equation has no real solutions")
    if not isinstance(symbolic, sp.Set) and symbolic.has(sp.zoo, sp.nan, sp.I):
        return done(VerificationStatus.REJECTED, reason="answer is undefined or complex")

    try:
        numeric = _numeric_check(instance.task, symbolic, rng)
    except (UnsupportedExpression, ZeroDivisionError, ValueError, TypeError, OverflowError) as err:
        checks.append(CheckRecord(method="numeric", passed=False, detail=f"{err.__class__.__name__}: {err}"))
        return done(VerificationStatus.REJECTED, reason="independent numeric check could not run")
    checks.append(numeric)
    if not numeric.passed:
        return done(VerificationStatus.REJECTED, reason=f"symbolic and numeric answers disagree ({numeric.method})")

    if instance.claimed_answer is not None:
        claimed = _claimed_check(instance.task, instance.claimed_answer, symbolic, rng)
        checks.append(claimed)
        if not claimed.passed:
            return done(VerificationStatus.REJECTED, reason="generator's claimed answer is wrong")

    return done(VerificationStatus.VERIFIED, answer=symbolic)


def verify_problem(spec: MathProblemSpec, seed: int) -> MathVerification:
    try:
        instance = instantiate(spec, seed)
    except UnsupportedExpression as err:
        return MathVerification(status=VerificationStatus.REJECTED, reason=str(err))
    return verify_instance(instance)


def grade_answer(task: MathTask, answer_key: str, student: str, seed: int = 0) -> GradeResult:
    """Check a student's answer against a verified key. Equivalent forms are accepted."""
    rng = random.Random(seed)
    x = symbol(task.var)
    try:
        if task.kind == "solve":
            parts = [p for p in re.split(r"[,;]|\bor\b|\band\b", student) if p.strip()]
            parts = [re.sub(rf"^\s*{task.var}\s*=", "", p) for p in parts]
            got = sorted(_num(parse_math(p, ())) for p in parts)
            want = sorted(_num(parse_math(p, ())) for p in answer_key.split(","))
            ok = len(got) == len(want) and all(_close(a, b) for a, b in zip(got, want))
            return GradeResult(correct=ok, status="correct" if ok else "incorrect", method="root set comparison")
        s = parse_math(student, _vars(task))
        k = parse_math(answer_key, _vars(task))
    except UnsupportedExpression as err:
        return GradeResult(correct=None, status="unparseable", method="parse", detail=str(err))

    if task.kind == "integral_indefinite":
        # Any antiderivative is right: compare derivatives.
        integrand = parse_math(task.expr, _vars(task))
        if sp.simplify(sp.diff(s, x) - integrand) == 0:
            return GradeResult(correct=True, status="correct", method="d/dx of answer equals integrand")
        ok, detail = _same_function(s, k, x, rng, up_to_constant=True)
        return GradeResult(correct=ok, status="correct" if ok else "incorrect", method="numeric, up to a constant", detail=detail)

    if s.free_symbols - k.free_symbols:
        return GradeResult(correct=False, status="incorrect", method="variables", detail="answer has extra variables")
    if sp.simplify(s - k) == 0:
        return GradeResult(correct=True, status="correct", method="symbolic equivalence")
    if not k.free_symbols:
        if k in (sp.oo, -sp.oo) or s in (sp.oo, -sp.oo):
            ok = s == k
        else:
            ok = _close(_num(s), _num(k))
        return GradeResult(correct=ok, status="correct" if ok else "incorrect", method="numeric value")
    ok, detail = _same_function(s, k, x, rng)
    return GradeResult(correct=ok, status="correct" if ok else "incorrect", method="numeric sampling", detail=detail)
