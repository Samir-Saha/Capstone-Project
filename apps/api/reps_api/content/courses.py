"""Built-in practice courses.

Every question is a template. Each time the boss asks one, a fresh instance is
drawn and verified by the math engine (symbolic + independent numeric check, plus
the claimed key below). An instance that fails is thrown away and logged.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from reps_api.verification.math_engine import MathProblemSpec, MathTask, ParamSpec

EXACT = "Exact form, like 3x^2 + cos(x), sqrt(2)/2 or ln(3)"
ROOTS = "All solutions, separated by commas, like 2, -3"
DECIMAL = "A number. Rounded answers within 1% count."


class QuestionTemplate(BaseModel):
    id: str
    topic: str
    difficulty: int = Field(ge=1, le=3)
    spec: MathProblemSpec
    hint: str
    method: str  # shown after answering; may use {params}
    answer_format: str = EXACT
    rel_tol: float | None = None


class TopicDef(BaseModel):
    key: str
    name: str
    description: str


class Ability(BaseModel):
    """A boss ability hits your hearts, never the boss's HP: HP always equals the
    mastery gap, so abilities change the stakes of a topic, not the scoreboard."""

    name: str
    topic: str  # topic key
    text: str


class CourseDef(BaseModel):
    id: str
    name: str
    code: str
    boss_name: str
    topics: list[TopicDef]
    templates: list[QuestionTemplate]
    ability: Ability | None = None


def P(lo: int, hi: int, exclude: list[int] | None = None) -> ParamSpec:
    return ParamSpec(min=lo, max=hi, exclude=exclude or [])


def T(
    id: str,
    topic: str,
    difficulty: int,
    prompt: str,
    task: dict,
    claimed: str | None,
    hint: str,
    method: str,
    params: dict[str, ParamSpec] | None = None,
    answer_format: str = EXACT,
    rel_tol: float | None = None,
) -> QuestionTemplate:
    return QuestionTemplate(
        id=id,
        topic=topic,
        difficulty=difficulty,
        spec=MathProblemSpec(statement=prompt, params=params or {}, task=MathTask(**task), claimed_answer=claimed),
        hint=hint,
        method=method,
        answer_format=answer_format,
        rel_tol=rel_tol,
    )


CALCULUS = CourseDef(
    id="calc-1",
    name="Calculus I",
    code="MATH 151",
    boss_name="Vexis, the Limitless",
    ability=Ability(name="Limitless Gaze", topic="limits", text="Missing a Limits question costs 2 hearts."),
    topics=[
        TopicDef(key="limits", name="Limits", description="Evaluating limits at a point and at infinity"),
        TopicDef(key="basic_rules", name="Derivative rules", description="Power, sum, and trig derivatives"),
        TopicDef(key="chain_product", name="Chain and product rule", description="Composite functions and products"),
        TopicDef(key="definite", name="Definite integrals", description="Areas with the fundamental theorem"),
        TopicDef(key="antiderivatives", name="Antiderivatives", description="Indefinite integrals and integration by parts"),
        TopicDef(key="equations", name="Solving equations", description="Polynomial equations with real roots"),
    ],
    templates=[
        # limits
        T(
            "lim-sin-ax",
            "limits",
            1,
            "Evaluate the limit.",
            {"kind": "limit", "expr": "sin({a}*x)/x", "at": "0"},
            "{a}",
            "Rewrite as a · sin(ax)/(ax) and use lim sin(u)/u = 1.",
            "sin({a}x)/x = {a} · sin({a}x)/({a}x), and sin(u)/u → 1, so the limit is {a}.",
            {"a": P(2, 9)},
        ),
        T(
            "lim-factor",
            "limits",
            1,
            "Evaluate the limit.",
            {"kind": "limit", "expr": "(x^2 - {a}^2)/(x - {a})", "at": "{a}"},
            "2*{a}",
            "Factor the numerator as a difference of squares.",
            "x² − {a}² = (x − {a})(x + {a}). Cancel, then plug in x = {a} to get 2·{a}.",
            {"a": P(1, 9)},
        ),
        T(
            "lim-inf-rational",
            "limits",
            2,
            "Evaluate the limit.",
            {"kind": "limit", "expr": "({a}*x^2 + {b}*x)/({c}*x^2 + 1)", "at": "oo"},
            "{a}/{c}",
            "Divide top and bottom by the highest power of x.",
            "Only the x² terms matter as x → ∞, so the limit is {a}/{c}.",
            {"a": P(1, 9), "b": P(1, 9), "c": P(2, 7)},
        ),
        # basic rules
        T(
            "d-power",
            "basic_rules",
            1,
            "Find the derivative.",
            {"kind": "derivative", "expr": "{a}*x^{n} + {b}*x"},
            "{a}*{n}*x^({n}-1) + {b}",
            "Power rule: d/dx xⁿ = n·xⁿ⁻¹.",
            "Apply the power rule term by term: {a}·{n}·x^({n}−1) + {b}.",
            {"a": P(2, 9), "n": P(2, 6), "b": P(1, 9)},
        ),
        T(
            "d-trig",
            "basic_rules",
            1,
            "Find the derivative.",
            {"kind": "derivative", "expr": "{a}*sin(x) + {b}*cos(x)"},
            "{a}*cos(x) - {b}*sin(x)",
            "d/dx sin x = cos x and d/dx cos x = −sin x.",
            "Differentiate each term: {a}cos(x) − {b}sin(x).",
            {"a": P(2, 9), "b": P(2, 9)},
        ),
        T(
            "d-poly-at",
            "basic_rules",
            2,
            "Find the value of the derivative.",
            {"kind": "derivative_at", "expr": "x^3 - {a}*x^2 + {b}*x", "at": "{c}"},
            None,
            "Differentiate first, then substitute.",
            "f′(x) = 3x² − 2·{a}x + {b}. Substitute x = {c}.",
            {"a": P(1, 6), "b": P(1, 9), "c": P(-3, 3)},
        ),
        # chain and product
        T(
            "d-chain-sin",
            "chain_product",
            2,
            "Find the derivative.",
            {"kind": "derivative", "expr": "sin({a}*x^2)"},
            "2*{a}*x*cos({a}*x^2)",
            "Outer function sin(u), inner u = ax². Multiply by du/dx.",
            "cos({a}x²) · d/dx({a}x²) = 2·{a}x·cos({a}x²).",
            {"a": P(2, 9)},
        ),
        T(
            "d-product-exp",
            "chain_product",
            2,
            "Find the derivative.",
            {"kind": "derivative", "expr": "x^{n}*exp({a}*x)"},
            "{n}*x^({n}-1)*exp({a}*x) + {a}*x^{n}*exp({a}*x)",
            "Product rule: (uv)′ = u′v + uv′.",
            "u = x^{n}, v = e^({a}x): {n}x^({n}−1)e^({a}x) + {a}x^{n}e^({a}x).",
            {"n": P(2, 4), "a": P(2, 5)},
        ),
        T(
            "d-chain-power-at",
            "chain_product",
            3,
            "Find the value of the derivative.",
            {"kind": "derivative_at", "expr": "({a}*x + 1)^{n}", "at": "0"},
            "{n}*{a}",
            "Chain rule: d/dx (ax + 1)ⁿ = n(ax + 1)ⁿ⁻¹ · a.",
            "f′(x) = {n}({a}x + 1)^({n}−1) · {a}. At x = 0 that's {n}·{a}.",
            {"a": P(2, 6), "n": P(3, 6)},
        ),
        # definite integrals
        T(
            "int-poly",
            "definite",
            1,
            "Evaluate the integral.",
            {"kind": "integral_definite", "expr": "{a}*x^2", "lower": "0", "upper": "{b}"},
            "{a}*{b}^3/3",
            "An antiderivative of x² is x³/3.",
            "[{a}x³/3] from 0 to {b} = {a}·{b}³/3.",
            {"a": P(1, 9), "b": P(1, 5)},
        ),
        T(
            "int-sin",
            "definite",
            2,
            "Evaluate the integral.",
            {"kind": "integral_definite", "expr": "{a}*sin(x)", "lower": "0", "upper": "pi"},
            "2*{a}",
            "An antiderivative of sin x is −cos x.",
            "[−{a}cos x] from 0 to π = {a} + {a} = 2·{a}.",
            {"a": P(1, 9)},
        ),
        T(
            "int-recip",
            "definite",
            2,
            "Evaluate the integral.",
            {"kind": "integral_definite", "expr": "{a}/x", "lower": "1", "upper": "{b}"},
            "{a}*ln({b})",
            "An antiderivative of 1/x is ln|x|.",
            "[{a} ln x] from 1 to {b} = {a}·ln({b}) − 0.",
            {"a": P(1, 6), "b": P(2, 9)},
        ),
        # antiderivatives
        T(
            "anti-power",
            "antiderivatives",
            1,
            "Find an antiderivative.",
            {"kind": "integral_indefinite", "expr": "{a}*x^{n}"},
            "{a}*x^({n}+1)/({n}+1)",
            "Reverse power rule: ∫xⁿ dx = xⁿ⁺¹/(n+1).",
            "{a}·x^({n}+1)/({n}+1), plus any constant.",
            {"a": P(1, 9), "n": P(2, 6)},
        ),
        T(
            "anti-cos",
            "antiderivatives",
            2,
            "Find an antiderivative.",
            {"kind": "integral_indefinite", "expr": "cos({a}*x)"},
            "sin({a}*x)/{a}",
            "Undo the chain rule: divide by the inner derivative.",
            "sin({a}x)/{a}, plus any constant.",
            {"a": P(2, 9)},
        ),
        T(
            "anti-parts",
            "antiderivatives",
            3,
            "Find an antiderivative.",
            {"kind": "integral_indefinite", "expr": "x*exp({a}*x)"},
            "x*exp({a}*x)/{a} - exp({a}*x)/{a}^2",
            "Integration by parts with u = x, dv = e^(ax) dx.",
            "u = x, v = e^({a}x)/{a}: x·e^({a}x)/{a} − e^({a}x)/{a}², plus any constant.",
            {"a": P(2, 5)},
        ),
        # equations
        T(
            "solve-quadratic",
            "equations",
            1,
            "Solve for x.",
            {"kind": "solve", "expr": "(x - {r})*(x + {s})"},
            "{r}, -{s}",
            "Find two numbers that multiply to the constant term and add to the x coefficient.",
            "It factors as (x − {r})(x + {s}), so x = {r} or x = −{s}.",
            {"r": P(1, 8), "s": P(1, 8)},
            answer_format=ROOTS,
        ),
        T(
            "solve-shifted-square",
            "equations",
            2,
            "Solve for x.",
            {"kind": "solve", "expr": "(x - {h})^2 - {k}^2"},
            "{h} + {k}, {h} - {k}",
            "Move the constant over and take square roots of both sides.",
            "(x − {h})² = {k}², so x − {h} = ±{k}.",
            {"h": P(-5, 5), "k": P(1, 6)},
            answer_format=ROOTS,
        ),
    ],
)

G = "Use g = 9.8 m/s²."

PHYSICS = CourseDef(
    id="phys-kinematics",
    name="Physics I: Kinematics",
    code="PHYS 203",
    boss_name="Kinetor, the Unstoppable",
    ability=Ability(name="Momentum", topic="accel", text="Missing a Constant acceleration question costs 2 hearts."),
    topics=[
        TopicDef(key="uniform", name="Uniform motion", description="Constant velocity: distance, speed, time"),
        TopicDef(key="accel", name="Constant acceleration", description="The kinematic equations"),
        TopicDef(key="freefall", name="Free fall and projectiles", description="Motion under gravity"),
    ],
    templates=[
        T(
            "uniform-distance",
            "uniform",
            1,
            "A cyclist rides at {v} m/s for {t} s. How far do they travel, in meters?",
            {"kind": "evaluate", "expr": "{v}*{t}"},
            "{v}*{t}",
            "Distance = speed × time.",
            "d = v·t = {v} × {t}.",
            {"v": P(3, 15), "t": P(10, 90)},
            DECIMAL,
            0.01,
        ),
        T(
            "uniform-time",
            "uniform",
            1,
            "A train covers {d} m at a steady {v} m/s. How many seconds does it take?",
            {"kind": "evaluate", "expr": "{d}/{v}"},
            None,
            "Time = distance ÷ speed.",
            "t = d / v = {d} / {v}.",
            {"d": P(200, 2000), "v": P(10, 40)},
            DECIMAL,
            0.01,
        ),
        T(
            "accel-displacement",
            "accel",
            2,
            "A car moving at {v} m/s accelerates at {a} m/s² for {t} s. How far does it travel in that time, in meters?",
            {"kind": "evaluate", "expr": "{v}*{t} + {a}*{t}^2/2"},
            None,
            "Use x = v₀t + ½at².",
            "x = {v}·{t} + ½·{a}·{t}².",
            {"v": P(0, 20), "a": P(1, 6), "t": P(2, 12)},
            DECIMAL,
            0.01,
        ),
        T(
            "accel-final-speed",
            "accel",
            2,
            "A sprinter starts at {v} m/s and accelerates at {a} m/s² over {d} m. What is the final speed, in m/s?",
            {"kind": "evaluate", "expr": "sqrt({v}^2 + 2*{a}*{d})"},
            None,
            "Use v² = v₀² + 2a·Δx, which needs no time.",
            "v = √({v}² + 2·{a}·{d}).",
            {"v": P(0, 8), "a": P(1, 5), "d": P(5, 40)},
            DECIMAL,
            0.01,
        ),
        T(
            "accel-stop-time",
            "accel",
            1,
            "A bike moving at {v} m/s brakes at a constant {a} m/s² until it stops. How many seconds does that take?",
            {"kind": "evaluate", "expr": "{v}/{a}"},
            None,
            "Use v = v₀ + at with final speed 0.",
            "0 = {v} − {a}·t, so t = {v}/{a}.",
            {"v": P(6, 30), "a": P(2, 8)},
            DECIMAL,
            0.01,
        ),
        T(
            "fall-distance",
            "freefall",
            1,
            f"A stone is dropped from rest and falls for {{t}} s. How far does it fall, in meters? {G}",
            {"kind": "evaluate", "expr": "49*{t}^2/10"},
            None,
            "Starting from rest, y = ½gt².",
            "y = ½ · 9.8 · {t}² = 4.9·{t}².",
            {"t": P(1, 6)},
            DECIMAL,
            0.01,
        ),
        T(
            "fall-up-time",
            "freefall",
            2,
            f"A ball is thrown straight up at {{v}} m/s. How many seconds until it lands back in your hand? {G}",
            {"kind": "evaluate", "expr": "2*{v}*10/98"},
            None,
            "Time up equals time down; at the top, velocity is 0.",
            "Time to the top is {v}/9.8, so the round trip is 2·{v}/9.8.",
            {"v": P(5, 30)},
            DECIMAL,
            0.01,
        ),
        T(
            "fall-max-height",
            "freefall",
            3,
            f"A ball is launched straight up at {{v}} m/s. How high does it rise, in meters? {G}",
            {"kind": "evaluate", "expr": "{v}^2*10/(2*98)"},
            None,
            "At the top v = 0. Use v² = v₀² − 2gh.",
            "h = {v}² / (2 · 9.8).",
            {"v": P(5, 30)},
            DECIMAL,
            0.01,
        ),
    ],
)

BUILTIN_COURSES = [CALCULUS, PHYSICS]
