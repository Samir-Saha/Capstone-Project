"""Whitelisted parsing of math strings into SymPy expressions.

Model-generated and student-typed math never reaches eval/exec directly. The string
is checked character by character and identifier by identifier, parsed without
evaluation, checked for oversized numbers and exponents, and only then evaluated.
"""

from __future__ import annotations

import re

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication,
    parse_expr,
    standard_transformations,
)

MAX_LENGTH = 300
MAX_EXPONENT = 60
MAX_INTEGER = 10**12

_ALLOWED_CHARS = re.compile(r"^[0-9A-Za-z\s.+\-*/^(),=]*$")
_IDENT = re.compile(r"[A-Za-z]+")

FUNCTIONS: dict[str, object] = {
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "sec": sp.sec,
    "csc": sp.csc,
    "cot": sp.cot,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "exp": sp.exp,
    "log": sp.log,
    "ln": sp.log,
    "sqrt": sp.sqrt,
    "Abs": sp.Abs,
    "abs": sp.Abs,
}
CONSTANTS: dict[str, object] = {"pi": sp.pi, "E": sp.E, "e": sp.E, "oo": sp.oo, "inf": sp.oo}

DEFAULT_VARIABLES = ("x", "y", "z", "t", "n", "k")

# Names parse_expr's generated code needs. Nothing else from builtins is reachable.
_PARSER_GLOBALS = {
    "Integer": sp.Integer,
    "Float": sp.Float,
    "Rational": sp.Rational,
    "Symbol": sp.Symbol,
    # evaluate=False rewrites operators as explicit constructor calls
    "Add": sp.Add,
    "Mul": sp.Mul,
    "Pow": sp.Pow,
}


class UnsupportedExpression(ValueError):
    """The string is outside the safe, supported subset."""


def _check_text(text: str, variables: tuple[str, ...]) -> None:
    if not text or not text.strip():
        raise UnsupportedExpression("empty expression")
    if len(text) > MAX_LENGTH:
        raise UnsupportedExpression(f"expression longer than {MAX_LENGTH} characters")
    if not _ALLOWED_CHARS.match(text):
        raise UnsupportedExpression("expression contains characters outside the math subset")
    for name in _IDENT.findall(text):
        if name not in FUNCTIONS and name not in CONSTANTS and name not in variables:
            raise UnsupportedExpression(f"unknown name '{name}'")


def _check_tree(expr: sp.Basic) -> None:
    for node in sp.preorder_traversal(expr):
        if isinstance(node, sp.Integer) and abs(int(node)) > MAX_INTEGER:
            raise UnsupportedExpression("number too large")
        if isinstance(node, sp.Pow):
            exponent = node.exp
            if exponent.is_number:
                try:
                    if abs(float(exponent)) > MAX_EXPONENT:
                        raise UnsupportedExpression("exponent too large")
                except TypeError as err:  # complex exponent
                    raise UnsupportedExpression("complex exponent") from err


def _parse_side(text: str, variables: tuple[str, ...]) -> sp.Expr:
    local_dict: dict[str, object] = {**FUNCTIONS, **CONSTANTS}
    local_dict.update({v: sp.Symbol(v, real=True) for v in variables})
    transformations = standard_transformations + (implicit_multiplication, convert_xor)
    try:
        unevaluated = parse_expr(
            text,
            local_dict=local_dict,
            global_dict=dict(_PARSER_GLOBALS),
            transformations=transformations,
            evaluate=False,
        )
    except Exception as err:  # SymPy raises a zoo of error types on bad input
        raise UnsupportedExpression(f"could not parse: {err.__class__.__name__}") from err
    if not isinstance(unevaluated, sp.Basic):
        raise UnsupportedExpression("not a math expression")
    _check_tree(unevaluated)
    try:
        evaluated = parse_expr(
            text,
            local_dict=local_dict,
            global_dict=dict(_PARSER_GLOBALS),
            transformations=transformations,
            evaluate=True,
        )
    except Exception as err:
        raise UnsupportedExpression(f"could not evaluate: {err.__class__.__name__}") from err
    result = sp.sympify(evaluated)
    if result.has(sp.zoo, sp.nan):
        raise UnsupportedExpression("expression is undefined (division by zero or similar)")
    return result


def parse_math(text: str, variables: tuple[str, ...] = DEFAULT_VARIABLES) -> sp.Expr:
    """Parse an expression. An equation `lhs = rhs` is returned as `lhs - rhs`."""
    _check_text(text, variables)
    if text.count("=") > 1:
        raise UnsupportedExpression("more than one '='")
    if "=" in text:
        lhs, rhs = text.split("=")
        return _parse_side(lhs, variables) - _parse_side(rhs, variables)
    return _parse_side(text, variables)


def symbol(name: str) -> sp.Symbol:
    """The symbol parse_math creates for a variable name, so results compare equal."""
    return sp.Symbol(name, real=True)


def to_latex(text: str, variables: tuple[str, ...] = DEFAULT_VARIABLES) -> str:
    """Render what the student typed without simplifying it (2*(18) stays 2 · 18).
    Same safety checks as parse_math."""
    _check_text(text, variables)
    local_dict: dict[str, object] = {**FUNCTIONS, **CONSTANTS}
    local_dict.update({v: sp.Symbol(v, real=True) for v in variables})
    transformations = standard_transformations + (implicit_multiplication, convert_xor)
    sides = []
    for side in text.split("="):
        if not side.strip():
            continue
        try:
            expr = parse_expr(side, local_dict=local_dict, global_dict=dict(_PARSER_GLOBALS), transformations=transformations, evaluate=False)
        except Exception as err:
            raise UnsupportedExpression(f"could not parse: {err.__class__.__name__}") from err
        _check_tree(expr)
        sides.append(sp.latex(expr))
    if not sides:
        raise UnsupportedExpression("empty expression")
    return " = ".join(sides)
