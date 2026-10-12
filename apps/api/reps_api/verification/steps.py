"""Show-your-work: check a student's working line by line.

Each line is classified against what the problem allows at that point:

  problem       a rewrite of the expression you were given (factoring, cancelling)
  intermediate  e.g. the derivative before plugging in, or an antiderivative
  answer        equal to the verified answer key
  computation   a numeric line in a word problem (checked for internal consistency)
  formula       uses named quantities (d = v*t); shown, not checked
  equation      for "solve" problems: must have the same real solutions as the original

The first line that matches nothing is where the work went wrong. A short
diagnosis compares it to the answer: off by a factor, a sign flip, a missing
constant, or a lost or extra solution.

Everything is decided by SymPy and numeric evaluation. No model is involved.
"""

from __future__ import annotations

import random
import re
from fractions import Fraction
from typing import Literal

import mpmath
import sympy as sp
from pydantic import BaseModel

from .math_engine import MathTask, _close, _fn, _num, _real_finite, _sample_points, _vars
from .safe_math import UnsupportedExpression, parse_math, symbol, to_latex

MAX_LINES = 20
Role = Literal["problem", "intermediate", "answer", "computation", "formula", "equation"]
Status = Literal["ok", "error", "unchecked", "unreadable"]


class StepLine(BaseModel):
    index: int
    text: str
    latex: str | None = None
    status: Status
    role: Role | None = None
    note: str | None = None


class StepReport(BaseModel):
    lines: list[StepLine]
    first_error: int | None
    checked: int
    summary: str


# ------------------------------------------------------------------ helpers


def _nice(value: float) -> str:
    frac = Fraction(value).limit_denominator(12)
    if abs(float(frac) - value) < 1e-9:
        return str(frac.numerator) if frac.denominator == 1 else f"{frac.numerator}/{frac.denominator}"
    return f"{value:.4g}"


def _values(a: sp.Expr, b: sp.Expr, x: sp.Symbol, rng: random.Random) -> list[tuple[float, float]]:
    if not a.free_symbols and not b.free_symbols:
        try:
            va, vb = _num(a), _num(b)
        except (UnsupportedExpression, TypeError, ValueError):
            return []
        return [(va, vb)] if _real_finite([va, vb]) else []
    fa, fb = _fn(a, x), _fn(b, x)
    out = []
    for pt in _sample_points(rng, 14):
        try:
            va, vb = fa(pt), fb(pt)
        except (ZeroDivisionError, ValueError, TypeError, OverflowError):
            continue
        if _real_finite([va, vb]):
            out.append((mpmath.re(va), mpmath.re(vb)))
        if len(out) >= 6:
            break
    return out


def relation(a: sp.Expr, b: sp.Expr, x: sp.Symbol, rng: random.Random) -> tuple[str, float | None]:
    """How a relates to b: equal, negated, factor k, offset c, or unrelated."""
    if (a.free_symbols or b.free_symbols) and sp.simplify(a - b) == 0:
        return "equal", None
    pairs = _values(a, b, x, rng)
    if not pairs or (len(pairs) < 3 and (a.free_symbols or b.free_symbols)):
        return "unknown", None
    if all(_close(p, q) for p, q in pairs):
        return "equal", None
    if all(_close(p, -q) for p, q in pairs) and any(abs(q) > 1e-9 for _, q in pairs):
        return "negated", None
    nonzero = [(p, q) for p, q in pairs if abs(q) > 1e-12]
    if nonzero:
        k = nonzero[0][0] / nonzero[0][1]
        if all(_close(p, k * q) for p, q in pairs) and abs(k) > 1e-12:
            return "factor", float(k)
    c = pairs[0][0] - pairs[0][1]
    if all(_close(p - q, c) for p, q in pairs):
        return "offset", float(c)
    return "unrelated", None


def _describe(rel: tuple[str, float | None], what: str) -> str | None:
    kind, k = rel
    if kind == "negated":
        return f"Sign error: this is the negative of {what}."
    if kind == "factor" and k is not None:
        return f"Off by a factor of {_nice(k)} from {what}. Check a coefficient or the chain rule."
    if kind == "offset" and k is not None:
        return f"Off by {_nice(k)} from {what}. Check a constant term."
    return None


_LABEL = re.compile(r"^\s*[A-Za-z][A-Za-z0-9_]*(\s*\([^)]*\))?\s*'*\s*$")
# Labels that announce a result ("f'(x) = ...", "y = ...") are checked like any line.
# Other names ("u = x", "dv = ...") introduce a substitution and aren't checked.
_RESULT_LABEL = re.compile(r"^\s*(y|f|g|h|F|G|I|A|ans|answer|result|d/dx.*)\s*(\([^)]*\))?\s*'*\s*$|'")


def _segments(text: str, variables: tuple[str, ...]) -> tuple[list[tuple[str, sp.Expr | None]], bool, str | None]:
    """Split "label = a = b" into parsed segments. Returns (segments, has_symbols).
    A segment that can't be parsed because it names quantities (v, d, f'(x)) is
    returned with None; a leading one is treated as a label and dropped."""
    text = text.strip().lstrip("=").strip()
    raw = [s for s in re.split(r"(?<![<>!=])=(?!=)", text)]
    segs: list[tuple[str, sp.Expr | None]] = []
    symbolic = False
    label = None
    for i, seg in enumerate(raw):
        seg = seg.strip()
        if not seg:
            continue
        try:
            segs.append((seg, parse_math(seg, variables)))
        except UnsupportedExpression as err:
            if i == 0 and len(raw) > 1 and (_LABEL.match(seg) or "'" in seg or "unknown name" in str(err)):
                label = seg  # a label like "d", "f'(x)", "y", "u"
                continue
            if "unknown name" in str(err):
                symbolic = True
                segs.append((seg, None))
            else:
                raise
    return segs, symbolic, label


def _latex(segs: list[tuple[str, sp.Expr | None]], variables: tuple[str, ...] = ("x", "y", "z", "t", "n", "k")) -> str | None:
    parts = []
    for raw, expr in segs:
        if expr is None:
            parts.append(r"\text{" + re.sub(r"[{}\\]", "", raw) + "}")
            continue
        try:
            parts.append(to_latex(raw, variables))  # as typed, not simplified
        except UnsupportedExpression:
            parts.append(sp.latex(expr))
    return " = ".join(parts) if parts else None


# ------------------------------------------------------------------ targets


def _targets(task: MathTask, key: sp.Expr) -> dict[str, sp.Expr]:
    x = symbol(task.var)
    f = parse_math(task.expr, _vars(task))
    if task.kind == "derivative_at":
        return {"problem": f, "intermediate": sp.diff(f, x, task.order), "answer": key}
    if task.kind in ("derivative",):
        return {"problem": f, "answer": key}
    if task.kind == "integral_definite":
        return {"problem": f, "answer": key}  # antiderivatives are checked by differentiating
    if task.kind == "integral_indefinite":
        return {"problem": f}  # answer = any antiderivative
    if task.kind == "limit":
        return {"problem": f, "answer": key}
    return {"answer": key}  # evaluate


def _is_antiderivative(expr: sp.Expr, integrand: sp.Expr, x: sp.Symbol, rng: random.Random) -> bool:
    if not expr.free_symbols:
        return False
    return relation(sp.diff(expr, x), integrand, x, rng)[0] == "equal"


def _classify(task: MathTask, expr: sp.Expr, targets: dict[str, sp.Expr], rng: random.Random) -> Role | None:
    x = symbol(task.var)
    if task.kind == "integral_indefinite":
        if _is_antiderivative(expr, targets["problem"], x, rng):
            return "answer"
    if "answer" in targets and relation(expr, targets["answer"], x, rng)[0] == "equal":
        return "answer"
    if task.kind == "integral_definite" and _is_antiderivative(expr, targets["problem"], x, rng):
        return "intermediate"
    if "intermediate" in targets and relation(expr, targets["intermediate"], x, rng)[0] == "equal":
        return "intermediate"
    if "problem" in targets and relation(expr, targets["problem"], x, rng)[0] == "equal":
        return "problem"
    return None


def _diagnose(task: MathTask, expr: sp.Expr, targets: dict[str, sp.Expr], rng: random.Random) -> str:
    x = symbol(task.var)
    if task.kind == "integral_indefinite" and expr.free_symbols:
        note = _describe(relation(sp.diff(expr, x), targets["problem"], x, rng), "the integrand when you differentiate it")
        if note:
            return note
    for name, label in (("answer", "the correct answer"), ("intermediate", "the derivative"), ("problem", "the original expression")):
        if name in targets:
            note = _describe(relation(expr, targets[name], x, rng), label)
            if note:
                return note
    return "This doesn't follow from the problem or your previous line."


# ------------------------------------------------------------------ solve


def _root_set(text: str, task: MathTask) -> list[float] | None:
    x = symbol(task.var)
    roots: list[float] = []
    for part in re.split(r"\bor\b|,|;", text):
        part = part.strip()
        if not part:
            continue
        expr = parse_math(part, _vars(task))  # "a = b" becomes a - b
        if expr.free_symbols - {x}:
            raise UnsupportedExpression("unknown variable")
        if not expr.free_symbols and "=" not in part:
            roots.append(float(_num(expr)))
            continue
        sol = sp.solveset(expr, x, domain=sp.S.Reals)
        if not isinstance(sol, sp.FiniteSet):
            return None
        roots += [float(_num(r)) for r in sol]
    out: list[float] = []
    for r in sorted(roots):
        if not out or abs(out[-1] - r) > 1e-7:
            out.append(r)
    return out


def _check_solve(task: MathTask, key: str, lines: list[str]) -> list[StepLine]:
    want = sorted(float(_num(parse_math(k, ()))) for k in key.split(","))
    result = []
    for i, text in enumerate(lines):
        try:
            got = _root_set(text, task)
            latex = r" \;\text{or}\; ".join(to_latex(part, _vars(task)) for part in re.split(r"\bor\b|,", text) if part.strip())
        except (UnsupportedExpression, TypeError, ValueError):
            result.append(StepLine(index=i, text=text, status="unreadable", note="Couldn't read this line."))
            continue
        if got is None:
            result.append(StepLine(index=i, text=text, latex=latex, status="unchecked", role="equation", note="Infinitely many solutions; not checked."))
            continue
        same = len(got) == len(want) and all(abs(a - b) < 1e-6 for a, b in zip(got, want))
        if same:
            result.append(StepLine(index=i, text=text, latex=latex, status="ok", role="equation"))
            continue
        lost = [w for w in want if not any(abs(w - g) < 1e-6 for g in got)]
        extra = [g for g in got if not any(abs(w - g) < 1e-6 for w in want)]
        if lost and not extra:
            note = f"You lost a solution here: {', '.join(_nice(v) for v in lost)} also works."
        elif extra and not lost:
            note = f"This line adds a solution that doesn't satisfy the original: {', '.join(_nice(v) for v in extra)}."
        else:
            note = "This line has different solutions than the original equation."
        result.append(StepLine(index=i, text=text, latex=latex, status="error", role="equation", note=note))
    return result


# ------------------------------------------------------------------ main


def check_steps(task: MathTask, answer_key: str, lines: list[str], seed: int = 0, rel_tol: float | None = None) -> StepReport:
    rng = random.Random(seed)
    lines = [ln for ln in (s.strip() for s in lines[:MAX_LINES]) if ln]
    if task.kind == "solve":
        checked = _check_solve(task, answer_key, lines)
    else:
        checked = []
        variables = _vars(task) if task.kind != "evaluate" else ()
        key = parse_math(answer_key, _vars(task))
        targets = _targets(task, key)
        for i, text in enumerate(lines):
            try:
                segs, symbolic, label = _segments(text, variables)
            except UnsupportedExpression:
                checked.append(StepLine(index=i, text=text, status="unreadable", note="Couldn't read this line."))
                continue
            latex = _latex(segs, variables)
            parsed = [(raw, e) for raw, e in segs if e is not None]
            if not parsed:
                checked.append(StepLine(index=i, text=text, latex=latex, status="unchecked", role="formula", note="A formula with named quantities; not checked."))
                continue
            # 1) a chain inside the line must hold: a = b = c
            chain_note = None
            for (ra, a), (rb, b) in zip(parsed, parsed[1:]):
                rel = relation(b, a, symbol(task.var), rng)
                if rel[0] not in ("equal", "unknown"):
                    if not a.free_symbols and not b.free_symbols:
                        chain_note = f"{ra} is {_nice(float(_num(a)))}, not {_nice(float(_num(b)))}."
                    else:
                        chain_note = _describe(rel, "the left side") or f"{rb} isn't equal to {ra}."
                    break
            if chain_note:
                checked.append(StepLine(index=i, text=text, latex=latex, status="error", role="computation", note=chain_note))
                continue
            last = parsed[-1][1]
            if task.kind == "evaluate":
                is_last = i == len(lines) - 1
                if is_last:
                    ok = (
                        relation(last, key, symbol(task.var), rng)[0] == "equal"
                        if rel_tol is None
                        else (abs(float(_num(last)) - float(_num(key))) <= rel_tol * max(abs(float(_num(key))), 1e-9) if not last.free_symbols else False)
                    )
                    checked.append(
                        StepLine(index=i, text=text, latex=latex, status="ok" if ok else "error", role="answer", note=None if ok else _diagnose(task, last, targets, rng))
                    )
                else:
                    checked.append(StepLine(index=i, text=text, latex=latex, status="ok", role="computation"))
                continue
            role = _classify(task, last, targets, rng)
            if role:
                checked.append(StepLine(index=i, text=text, latex=latex, status="ok", role=role))
            elif label and not _RESULT_LABEL.match(label):
                checked.append(StepLine(index=i, text=text, latex=latex, status="unchecked", role="formula", note=f"Defines {label.strip()}; not checked."))
            else:
                checked.append(StepLine(index=i, text=text, latex=latex, status="error", note=_diagnose(task, last, targets, rng)))

    first_error = next((ln.index for ln in checked if ln.status == "error"), None)
    n_checked = sum(1 for ln in checked if ln.status in ("ok", "error"))
    if first_error is not None:
        summary = f"Line {first_error + 1} is where it went wrong."
    elif checked and checked[-1].status == "ok" and checked[-1].role in ("answer", "equation"):
        summary = "Every checked line holds."
    elif n_checked:
        summary = "No mistakes found in the lines that could be checked."
    else:
        summary = "Nothing here could be checked."
    return StepReport(lines=checked, first_error=first_error, checked=n_checked, summary=summary)


def final_answer(task: MathTask, lines: list[str]) -> str:
    """The answer a show-your-work submission is graded on: the last line,
    minus any label, using the last segment of an a = b chain."""
    last = next((ln for ln in reversed(lines) if ln.strip()), "")
    if task.kind == "solve":
        return last
    parts = [p.strip() for p in re.split(r"(?<![<>!=])=(?!=)", last.strip().lstrip("=")) if p.strip()]
    return parts[-1] if parts else last
