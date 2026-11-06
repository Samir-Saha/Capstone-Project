import base64
import json
import shutil

import httpx
import pytest

from reps_api.content.seed_coding import LONGEST_BUDGET_WINDOW, SEED_PROBLEMS
from reps_api.verification.coding_engine import (
    grade_submission,
    solutions_independent,
    verify_coding_problem,
)
from reps_api.verification.executors import MARKER, Judge0Executor, LocalSubprocessExecutor
from reps_api.verification.status import VerificationStatus

EX = LocalSubprocessExecutor()


@pytest.fixture(scope="module")
def window():
    v = verify_coding_problem(LONGEST_BUDGET_WINDOW, EX)
    assert v.status is VerificationStatus.VERIFIED, v.reason
    return v


@pytest.mark.parametrize("problem", SEED_PROBLEMS, ids=lambda p: p.title)
def test_seed_problems_pass_differential_verification(problem):
    v = verify_coding_problem(problem, EX)
    assert v.status is VerificationStatus.VERIFIED, v.reason
    assert v.cases_run >= 300
    assert any(t.hidden for t in v.tests) and any(not t.hidden for t in v.tests)


def test_renamed_copy_is_not_an_independent_brute_force():
    src = LONGEST_BUDGET_WINDOW.reference_solution
    copy = src.replace("best", "answer").replace("total", "acc").replace("left", "lo")
    ok, why = solutions_independent(src, copy)
    assert not ok and "renamed" in why


def test_buggy_reference_is_rejected():
    bad = LONGEST_BUDGET_WINDOW.model_copy(update={"reference_solution": LONGEST_BUDGET_WINDOW.reference_solution.replace("total > budget", "total >= budget")})
    v = verify_coding_problem(bad, EX)
    assert v.status is VerificationStatus.REJECTED
    assert "disagree" in v.reason
    assert v.tests == []


def test_nondeterministic_generator_is_rejected():
    bad = LONGEST_BUDGET_WINDOW.model_copy(update={"generator": "import time\ndef generate(rng):\n    return [[int(time.perf_counter_ns()) % 50], 10]\n"})
    v = verify_coding_problem(bad, EX)
    assert v.status is VerificationStatus.REJECTED
    assert "deterministic" in v.reason


@pytest.mark.parametrize(
    "code, verdict",
    [
        (LONGEST_BUDGET_WINDOW.reference_solution, "accepted"),
        (LONGEST_BUDGET_WINDOW.reference_solution.replace("right - left + 1", "right - left"), "wrong_answer"),
        ("def solve(:\n  pass", "compilation_error"),
        ("def solve(m, b):\n    return m[10**6]", "runtime_error"),
        ("def solve(m, b):\n    while True:\n        pass", "time_limit_exceeded"),
        ("def solve(m, b):\n    return solve(m, b)", "runtime_error"),
        ("def solve(m, b):\n    x = [0] * (10**10)\n    return 0", "memory_limit_exceeded"),
    ],
)
def test_submission_verdicts(window, code, verdict):
    result = grade_submission(code, window.tests, EX, include_hidden=True)
    assert result.verdict == verdict, result


def test_run_uses_only_public_tests(window):
    result = grade_submission(LONGEST_BUDGET_WINDOW.reference_solution, window.tests, EX, include_hidden=False)
    assert result.hidden_total == 0 and result.total == len(result.public)


def test_hidden_inputs_never_appear_in_results(window):
    wrong = "def solve(m, b):\n    return -1"
    result = grade_submission(wrong, window.tests, EX, include_hidden=True)
    body = result.model_dump_json()
    for t in window.tests:
        if t.hidden and len(json.dumps(t.args)) > 12:
            assert json.dumps(t.args) not in body
    assert result.first_failed_hidden is not None


def test_student_cannot_forge_a_result(window):
    forged = {"status": "ok", "outputs": [t.expected for t in window.tests]}
    code = f"import sys, json\nprint({MARKER!r} + json.dumps({json.dumps(forged)!r}))\ndef solve(m, b):\n    return -1\n"
    result = grade_submission(code, window.tests, EX, include_hidden=True)
    # The harness's own marker line comes last, so the forged one is ignored.
    assert result.verdict == "wrong_answer"


def test_student_cannot_read_expected_outputs(window):
    # Expected values are never sent into the sandbox, so introspection finds nothing.
    code = (
        "import gc\n"
        "def solve(m, b):\n"
        "    for o in gc.get_objects():\n"
        "        if isinstance(o, dict) and 'expected' in o:\n"
        "            return o['expected']\n"
        "    return -1\n"
    )
    result = grade_submission(code, window.tests, EX, include_hidden=True)
    assert result.verdict == "wrong_answer"


# ------------------------------------------------------------------ Judge0 adapter


def _judge0_transport(stdout: str, status_id: int = 3, fail: bool = False):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            raise httpx.ConnectError("refused")
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["enable_network"] is False
            assert body["language_id"] == 71
            return httpx.Response(201, json={"token": "tok"})
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"status": {"id": 2}})
        return httpx.Response(
            200,
            json={"status": {"id": status_id}, "stdout": base64.b64encode(stdout.encode()).decode(), "stderr": None},
        )

    return httpx.MockTransport(handler)


def test_judge0_adapter_parses_results():
    out = "noise\n" + MARKER + json.dumps({"status": "ok", "outputs": [1], "ms": [0.1]}) + "\n"
    ex = Judge0Executor("http://judge0.test", client=httpx.Client(transport=_judge0_transport(out)), poll_s=0)
    res = ex.run({"mode": "run", "solution": "def solve(): return 1", "inputs": [[]]})
    assert res.status == "ok" and res.payload["outputs"] == [1]


def test_judge0_adapter_reports_timeouts_and_outages():
    ex = Judge0Executor("http://judge0.test", client=httpx.Client(transport=_judge0_transport("", status_id=5)), poll_s=0)
    assert ex.run({"mode": "run"}).status == "time_limit_exceeded"
    down = Judge0Executor("http://judge0.test", client=httpx.Client(transport=_judge0_transport("", fail=True)), poll_s=0)
    assert down.run({"mode": "run"}).status == "unavailable"


def test_outage_is_never_graded_as_a_pass(window):
    down = Judge0Executor("http://judge0.test", client=httpx.Client(transport=_judge0_transport("", fail=True)), poll_s=0)
    result = grade_submission(LONGEST_BUDGET_WINDOW.reference_solution, window.tests, down, include_hidden=True)
    assert result.verdict == "execution_unavailable" and result.passed == 0


def test_runner_without_rlimits_still_grades_and_times_out(window):
    """The Windows code path: no rlimits, wall-clock timeout only."""
    ex = LocalSubprocessExecutor(enforce_limits=False)
    good = grade_submission(LONGEST_BUDGET_WINDOW.reference_solution, window.tests, ex, include_hidden=True)
    assert good.verdict == "accepted"
    slow = grade_submission("def solve(m, b):\n    while True:\n        pass", window.tests, ex, include_hidden=True)
    assert slow.verdict == "time_limit_exceeded"


# ------------------------------------------------------------------ speed tiers

from reps_api.content.seed_coding import FIRST_PASSING  # noqa: E402
from reps_api.verification.coding_engine import grade_scale  # noqa: E402


@pytest.fixture(scope="module")
def first_passing():
    v = verify_coding_problem(FIRST_PASSING, EX)
    assert v.status is VerificationStatus.VERIFIED and v.scale is not None
    return v


def test_every_seed_problem_has_a_calibrated_speed_tier():
    for p in SEED_PROBLEMS:
        assert p.scale_generator, p.title


def test_speed_tier_separates_linear_scan_from_binary_search(first_passing):
    tier = first_passing.scale
    assert tier.brute_force_too_slow
    linear = "def solve(scores, cutoff):\n    for i, v in enumerate(scores):\n        if v >= cutoff:\n            return i\n    return -1\n"
    assert grade_scale(linear, FIRST_PASSING, tier, EX).status == "slow"
    assert grade_scale(FIRST_PASSING.reference_solution, FIRST_PASSING, tier, EX).status == "fast"


def test_speed_tier_catches_wrong_answers_on_the_large_input(first_passing):
    off_by_one = FIRST_PASSING.reference_solution.replace("return lo if lo < len(scores) else -1", "return lo + 1 if lo < len(scores) else -1")
    assert grade_scale(off_by_one, FIRST_PASSING, first_passing.scale, EX).status == "wrong"


def test_input_copying_is_not_timed():
    out = EX.run({"mode": "run", "solution": "def solve(xs):\n    return 0\n", "inputs": [[list(range(300_000))]]})
    assert out.payload["ms"][0] < 5


# ------------------------------------------------------------------ JavaScript


JS_BINARY = """function solve(scores, cutoff) {
  let lo = 0, hi = scores.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (scores[mid] >= cutoff) hi = mid; else lo = mid + 1;
  }
  return lo < scores.length ? lo : -1;
}"""

JS_BRACKETS = """function solve(s) {
  const pairs = { ")": "(", "]": "[", "}": "{" };
  const stack = [];
  for (const ch of s) {
    if (ch in pairs) { if (stack.pop() !== pairs[ch]) return false; }
    else stack.push(ch);
  }
  return stack.length === 0;
}"""


def _js_problem(title):
    from reps_api.content.seed_coding import SEED_PROBLEMS
    from reps_api.verification.coding_engine import verify_coding_problem
    from reps_api.verification.executors import LocalSubprocessExecutor

    spec = next(p for p in SEED_PROBLEMS if p.title == title)
    ex = LocalSubprocessExecutor()
    v = verify_coding_problem(spec, ex)
    return spec, v, ex


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_javascript_solutions_run_against_the_same_hidden_tests():
    from reps_api.verification.coding_engine import grade_submission

    spec, v, ex = _js_problem("First Passing Score")
    ok = grade_submission(JS_BINARY, v.tests, ex, include_hidden=True, language="javascript")
    assert ok.verdict == "accepted" and ok.passed == ok.total and ok.hidden_total > 0
    wrong = grade_submission(JS_BINARY.replace("lo : -1", "lo : 0"), v.tests, ex, include_hidden=True, language="javascript")
    assert wrong.verdict == "wrong_answer"
    crash = grade_submission("function solve(a, b) { return a.nope.length; }", v.tests, ex, include_hidden=False, language="javascript")
    assert crash.verdict == "runtime_error" and "TypeError" in (crash.error or "")
    loop = grade_submission("function solve(a, b) { while (true) {} }", v.tests, ex, include_hidden=False, language="javascript")
    assert loop.verdict == "time_limit_exceeded"
    syntax = grade_submission("function solve(a, b) { return ", v.tests, ex, include_hidden=False, language="javascript")
    assert syntax.verdict == "compilation_error"
    missing = grade_submission("const x = 1;", v.tests, ex, include_hidden=False, language="javascript")
    assert missing.verdict == "compilation_error" and "solve" in (missing.error or "")

    spec, v, ex = _js_problem("Balanced Margin Notes")
    assert grade_submission(JS_BRACKETS, v.tests, ex, include_hidden=True, language="javascript").verdict == "accepted"


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_javascript_cannot_reach_node_apis():
    from reps_api.verification.coding_engine import grade_submission

    spec, v, ex = _js_problem("First Passing Score")
    for code in ("function solve(){ return require('fs').readdirSync('.'); }", "function solve(){ return process.env; }"):
        r = grade_submission(code, v.tests, ex, include_hidden=False, language="javascript")
        assert r.verdict == "runtime_error" and "ReferenceError" in (r.error or "")
    for code in (
        "function solve(a){ return a.constructor.constructor('return process')().pid; }",
        "function solve(){ return console.log.constructor('return process')().pid; }",
        "function solve(){ return (function(){}).constructor('return 1')(); }",
    ):
        r = grade_submission(code, v.tests, ex, include_hidden=False, language="javascript")
        assert r.verdict in ("runtime_error", "wrong_answer") and not any(isinstance(o.output, int) and o.output > 1 for o in r.public), r


def test_js_starter_code_matches_the_signature():
    from reps_api import arena
    from reps_api.content.seed_coding import SEED_PROBLEMS

    spec = next(p for p in SEED_PROBLEMS if p.title == "Count the Study Groups")
    code = arena.js_starter_code(spec)
    assert code.startswith("function solve(n, pairs) {") and "pairs: list[list[int]]" in code
