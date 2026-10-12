import base64
import json

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
