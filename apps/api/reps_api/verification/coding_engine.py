"""Coding-problem verification (before publishing) and submission grading.

Publishing a problem requires:
  1. a reference solution and a brute-force solution that are structurally
     different (checked on the syntax tree with every name normalized away),
  2. a deterministic random input generator,
  3. agreement between reference and brute force on every edge case plus
     hundreds of seeded random inputs, run in the sandbox.

Hidden test outputs are then produced by running the verified reference solution,
not by asking a model what the answer should be.
"""

from __future__ import annotations

import ast
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from .executors import Executor
from .harness import _equal  # stdlib-only comparison shared with the sandbox
from .status import VerificationStatus


class CodingProblemSpec(BaseModel):
    title: str
    pattern: str  # "sliding window", "graphs", ...
    difficulty: Literal["easy", "medium", "hard"]
    statement: str
    signature: str  # e.g. "def solve(nums: list[int], k: int) -> int"
    reference_solution: str
    brute_force_solution: str
    generator: str  # defines generate(rng) -> list of args
    edge_cases: list[list[Any]] = Field(default_factory=list)
    public_examples: list[list[Any]] = Field(default_factory=list)
    unordered_output: bool = False
    # Speed tier: source defining generate_large() -> args, one big deterministic input
    # that an efficient solution handles quickly and a naive one doesn't.
    scale_generator: str | None = None


SCALE_FACTOR = 20  # a submission may take up to 20x the reference's time
SCALE_FLOOR_MS = 10.0


class ScaleTier(BaseModel):
    """Measured on this machine when the problem is verified, so the limit is self-calibrating."""

    reference_ms: float
    limit_ms: float
    reference_hash: str
    brute_force_too_slow: bool  # does the tier actually separate the two solutions?


class ScaleResult(BaseModel):
    status: Literal["fast", "slow", "wrong", "error"]
    ms: float | None = None
    limit_ms: float
    detail: str | None = None


class TestCase(BaseModel):
    args: list[Any]
    expected: Any
    hidden: bool


class CodingVerification(BaseModel):
    status: VerificationStatus
    reason: str | None = None
    cases_run: int = 0
    edge_cases: int = 0
    random_cases: int = 0
    seed: int
    executor: str
    duration_ms: int = 0
    tests: list[TestCase] = Field(default_factory=list)
    scale: ScaleTier | None = None
    detail: dict[str, Any] = Field(default_factory=dict)  # internal; never sent to students


class _Normalizer(ast.NodeTransformer):
    """Replace every identifier with its order of first appearance."""

    def __init__(self) -> None:
        self.names: dict[str, str] = {}

    def _n(self, name: str) -> str:
        return self.names.setdefault(name, f"v{len(self.names)}")

    def visit_Name(self, node: ast.Name) -> ast.AST:
        node.id = self._n(node.id)
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = self._n(node.arg)
        node.annotation = None
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        node.name = self._n(node.name)
        node.returns = None
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant):
            node.body = node.body[1:] or [ast.Pass()]
        self.generic_visit(node)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        return node


def structural_fingerprint(src: str) -> str:
    tree = ast.parse(src)
    tree = _Normalizer().visit(tree)
    return ast.dump(tree, annotate_fields=False, include_attributes=False)


def solutions_independent(reference: str, brute: str) -> tuple[bool, str]:
    try:
        a, b = structural_fingerprint(reference), structural_fingerprint(brute)
    except SyntaxError as err:
        return False, f"syntax error: {err.msg}"
    if a == b:
        return False, "brute force is the reference solution with renamed variables"
    return True, ""


def verify_coding_problem(
    spec: CodingProblemSpec,
    executor: Executor,
    seed: int = 1,
    n_random: int = 300,
    n_hidden: int = 40,
) -> CodingVerification:
    started = time.perf_counter()

    def finish(status: VerificationStatus, reason: str | None = None, **kw: Any) -> CodingVerification:
        return CodingVerification(
            status=status,
            reason=reason,
            seed=seed,
            executor=executor.name,
            duration_ms=int((time.perf_counter() - started) * 1000),
            **kw,
        )

    independent, why = solutions_independent(spec.reference_solution, spec.brute_force_solution)
    if not independent:
        return finish(VerificationStatus.REJECTED, why)

    diff = executor.run(
        {
            "mode": "differential",
            "reference": spec.reference_solution,
            "brute": spec.brute_force_solution,
            "generator": spec.generator,
            "edge_cases": spec.edge_cases,
            "n_random": n_random,
            "seed": seed,
            "unordered": spec.unordered_output,
        },
        cpu_seconds=20,
        memory_mb=768,
    )
    if diff.status != "ok":
        return finish(VerificationStatus.REJECTED, f"differential run failed: {diff.status}", detail={"stderr": diff.stderr})
    if not diff.payload.get("ok"):
        return finish(
            VerificationStatus.REJECTED,
            f"{diff.payload.get('stage')}: {diff.payload.get('error')}",
            cases_run=diff.payload.get("cases_run", 0),
            detail=diff.payload,
        )

    # Build the stored test suite from the verified reference.
    hidden_inputs: list[list[Any]] = [list(a) for a in spec.edge_cases]
    gen_job = {
        "mode": "run",
        "solution": spec.generator.replace("def generate(", "def _generate(") + "\nimport random as _r\ndef solve(i):\n    return _generate(_r.Random(i))\n",
        "inputs": [[seed + 100_000 + i] for i in range(n_hidden)],
    }
    gen = executor.run(gen_job, cpu_seconds=10, memory_mb=512)
    if gen.status != "ok" or gen.payload.get("status") != "ok":
        return finish(VerificationStatus.REJECTED, "could not generate hidden test inputs", detail=gen.payload)
    hidden_inputs += [list(a) for a in gen.payload["outputs"]]
    all_inputs = [list(a) for a in spec.public_examples] + hidden_inputs

    ref = executor.run({"mode": "run", "solution": spec.reference_solution, "inputs": all_inputs}, cpu_seconds=20, memory_mb=768)
    if ref.status != "ok" or ref.payload.get("status") != "ok":
        return finish(VerificationStatus.REJECTED, "reference failed while building tests", detail=ref.payload)
    outputs = ref.payload["outputs"]
    n_public = len(spec.public_examples)
    tests = [TestCase(args=a, expected=o, hidden=i >= n_public) for i, (a, o) in enumerate(zip(all_inputs, outputs))]

    tier = None
    if spec.scale_generator:
        job = {"mode": "scale", "solution": spec.reference_solution, "generator": spec.scale_generator, "unordered": spec.unordered_output}
        ref_scale = executor.run(job, cpu_seconds=30, memory_mb=1536)
        if ref_scale.status != "ok" or ref_scale.payload.get("status") != "ok":
            return finish(VerificationStatus.REJECTED, "reference failed on the speed-tier input", detail={"scale": ref_scale.payload or ref_scale.status})
        ref_ms = float(ref_scale.payload["ms"])
        limit = round(max(SCALE_FLOOR_MS, SCALE_FACTOR * ref_ms), 1)
        brute_job = {**job, "solution": spec.brute_force_solution}
        brute_scale = executor.run(brute_job, cpu_seconds=max(2, int(limit * 1.5 / 1000) + 1), memory_mb=1536)
        brute_slow = brute_scale.status != "ok" or brute_scale.payload.get("status") != "ok" or float(brute_scale.payload.get("ms", 0)) > limit
        tier = ScaleTier(reference_ms=ref_ms, limit_ms=limit, reference_hash=ref_scale.payload["output_hash"], brute_force_too_slow=brute_slow)

    return finish(
        VerificationStatus.VERIFIED,
        cases_run=diff.payload["cases_run"],
        edge_cases=diff.payload["edge_cases"],
        random_cases=diff.payload["random_cases"],
        tests=tests,
        scale=tier,
        detail={"reference_ms": diff.payload.get("reference_ms"), "brute_ms": diff.payload.get("brute_ms")},
    )


# ------------------------------------------------------------------- grading

Verdict = Literal[
    "accepted",
    "wrong_answer",
    "compilation_error",
    "runtime_error",
    "time_limit_exceeded",
    "memory_limit_exceeded",
    "execution_unavailable",
]


class PublicTestResult(BaseModel):
    index: int
    passed: bool
    args: list[Any]
    expected: Any
    output: Any | None


class SubmissionResult(BaseModel):
    """Safe to send to the browser: hidden inputs and outputs never appear here."""

    verdict: Verdict
    passed: int
    total: int
    public: list[PublicTestResult]
    hidden_passed: int
    hidden_total: int
    first_failed_hidden: int | None = None  # ordinal only, e.g. "hidden test 7"
    error: str | None = None
    runtime_ms: float | None = None
    executor: str
    scale: ScaleResult | None = None


def grade_scale(code: str, spec: CodingProblemSpec, tier: ScaleTier, executor: Executor) -> ScaleResult:
    job = {"mode": "scale", "solution": code, "generator": spec.scale_generator, "unordered": spec.unordered_output}
    res = executor.run(job, cpu_seconds=max(2, int(tier.limit_ms * 1.3 / 1000) + 2), memory_mb=1536)
    if res.status == "time_limit_exceeded":
        return ScaleResult(status="slow", limit_ms=tier.limit_ms, detail="didn't finish before the time limit")
    if res.status != "ok":
        return ScaleResult(status="error", limit_ms=tier.limit_ms, detail=res.status.replace("_", " "))
    payload = res.payload
    if payload.get("status") != "ok":
        return ScaleResult(status="error", limit_ms=tier.limit_ms, detail=payload.get("error") or payload.get("status"))
    ms = float(payload["ms"])
    if payload["output_hash"] != tier.reference_hash:
        return ScaleResult(status="wrong", ms=ms, limit_ms=tier.limit_ms, detail="wrong answer on the large input")
    return ScaleResult(status="fast" if ms <= tier.limit_ms else "slow", ms=round(ms, 1), limit_ms=tier.limit_ms)


def grade_submission(
    code: str,
    tests: list[TestCase],
    executor: Executor,
    include_hidden: bool,
    unordered: bool = False,
    language: str = "python",
) -> SubmissionResult:
    selected = [t for t in tests if include_hidden or not t.hidden]
    job = {"mode": "run", "solution": code, "inputs": [t.args for t in selected], "language": language}
    res = executor.run(job, cpu_seconds=5, memory_mb=256)
    hidden_total = sum(1 for t in selected if t.hidden)

    def empty(verdict: Verdict, error: str | None = None) -> SubmissionResult:
        return SubmissionResult(
            verdict=verdict,
            passed=0,
            total=len(selected),
            public=[],
            hidden_passed=0,
            hidden_total=hidden_total,
            error=error,
            executor=executor.name,
        )

    if res.status == "unavailable":
        return empty("execution_unavailable", "The code runner is unreachable. Nothing was graded.")
    if res.status in ("time_limit_exceeded", "memory_limit_exceeded"):
        return empty(res.status)  # type: ignore[arg-type]
    if res.status == "crashed":
        return empty("runtime_error", "Your program crashed the interpreter.")

    payload = res.payload
    run_status = payload.get("status")
    if run_status == "compilation_error":
        return empty("compilation_error", payload.get("error"))
    if run_status == "time_limit_exceeded":
        return empty("time_limit_exceeded")
    outputs: list[Any] = payload.get("outputs", [])

    public_results: list[PublicTestResult] = []
    passed = hidden_passed = 0
    first_failed_hidden: int | None = None
    hidden_ordinal = 0
    for i, test in enumerate(selected):
        produced = i < len(outputs)
        ok = produced and _equal(outputs[i], test.expected, unordered)
        if test.hidden:
            hidden_ordinal += 1
            if ok:
                hidden_passed += 1
            elif first_failed_hidden is None and produced:
                first_failed_hidden = hidden_ordinal
        else:
            public_results.append(
                PublicTestResult(index=len(public_results) + 1, passed=ok, args=test.args, expected=test.expected, output=outputs[i] if produced else None)
            )
        passed += int(ok)

    if run_status in ("runtime_error", "memory_limit_exceeded"):
        verdict: Verdict = run_status  # type: ignore[assignment]
        idx = payload.get("failed_index")
        if idx is not None and idx < len(selected) and selected[idx].hidden:
            first_failed_hidden = sum(1 for t in selected[: idx + 1] if t.hidden)
        error = payload.get("error") if idx is None or not selected[idx].hidden else _scrub(payload.get("error"))
    else:
        verdict = "accepted" if passed == len(selected) else "wrong_answer"
        error = None

    return SubmissionResult(
        verdict=verdict,
        passed=passed,
        total=len(selected),
        public=public_results,
        hidden_passed=hidden_passed,
        hidden_total=hidden_total,
        first_failed_hidden=first_failed_hidden,
        error=error,
        runtime_ms=sum(payload.get("ms", [])) or None,
        executor=executor.name,
    )


def _scrub(message: str | None) -> str | None:
    """Keep the exception type but drop text that could echo hidden input values."""
    if not message:
        return message
    return message.split(":", 1)[0] + " on a hidden test"
