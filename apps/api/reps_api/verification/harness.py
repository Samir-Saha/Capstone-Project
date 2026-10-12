"""Code-execution harness. Runs INSIDE the sandbox, never inside the API process.

Reads one JSON job from stdin and writes one JSON result line to stdout, prefixed
with a marker so stray prints from user code can't forge a result. The same file is
sent to Judge0 in production and run as a resource-limited subprocess in development.

This file must stay dependency-free (stdlib only): it runs on a bare interpreter.

Job shapes
  {"mode": "differential", "reference": src, "brute": src, "generator": src,
   "edge_cases": [[args...]], "n_random": 300, "seed": 1, "unordered": false}
  {"mode": "run", "solution": src, "inputs": [[args...], ...]}

Every solution defines solve(*args). A generator defines generate(rng) -> list of args.
"""

import copy
import json
import math
import random
import sys
import time
import traceback

MARKER = "@@REPS_RESULT@@"


def _load(src, name, required):
    namespace = {"__name__": "reps_" + name}
    code = compile(src, "<" + name + ">", "exec")
    exec(code, namespace)
    fn = namespace.get(required)
    if not callable(fn):
        raise NameError(name + " does not define " + required + "()")
    return fn


def _canon(value, unordered):
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list):
        items = [_canon(v, unordered) for v in value]
        if unordered:
            items.sort(key=lambda v: json.dumps(v, sort_keys=True))
        return items
    if isinstance(value, dict):
        return {str(k): _canon(v, unordered) for k, v in value.items()}
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return repr(value)
        return round(value, 6)
    return value


def _equal(a, b, unordered):
    return json.dumps(_canon(a, unordered), sort_keys=True) == json.dumps(_canon(b, unordered), sort_keys=True)


def _short(value, limit=300):
    text = json.dumps(value, default=repr)
    return text if len(text) <= limit else text[:limit] + "..."


def _emit(result):
    sys.stdout.write("\n" + MARKER + json.dumps(result, default=repr) + "\n")
    sys.stdout.flush()


def differential(job):
    try:
        ref = _load(job["reference"], "reference", "solve")
        brute = _load(job["brute"], "brute", "solve")
        gen = _load(job["generator"], "generator", "generate")
    except SyntaxError as err:
        return {"ok": False, "stage": "compile", "error": "SyntaxError: " + str(err)}
    except Exception as err:
        return {"ok": False, "stage": "load", "error": err.__class__.__name__ + ": " + str(err)}

    seed = int(job.get("seed", 1))
    n_random = int(job.get("n_random", 300))
    unordered = bool(job.get("unordered", False))

    # The generator must be deterministic for a seed, or failures can't be reproduced.
    try:
        first = [gen(random.Random(seed + i)) for i in range(5)]
        second = [gen(random.Random(seed + i)) for i in range(5)]
    except Exception as err:
        return {"ok": False, "stage": "generator", "error": err.__class__.__name__ + ": " + str(err)}
    if json.dumps(first, default=repr) != json.dumps(second, default=repr):
        return {"ok": False, "stage": "generator", "error": "generator is not deterministic for a fixed seed"}

    cases = [("edge", list(args)) for args in job.get("edge_cases", [])]
    for i in range(n_random):
        args = gen(random.Random(seed + i))
        if not isinstance(args, (list, tuple)):
            return {"ok": False, "stage": "generator", "error": "generate() must return a list of arguments"}
        cases.append(("random", list(args)))

    run = 0
    ref_time = 0.0
    brute_time = 0.0
    for kind, args in cases:
        try:
            t0 = time.perf_counter()
            expected = ref(*copy.deepcopy(args))
            t1 = time.perf_counter()
            actual = brute(*copy.deepcopy(args))
            t2 = time.perf_counter()
        except Exception as err:
            return {
                "ok": False,
                "stage": "execute",
                "error": err.__class__.__name__ + ": " + str(err),
                "case_kind": kind,
                "args": _short(args),
                "trace": traceback.format_exc(limit=3)[-800:],
                "cases_run": run,
            }
        ref_time += t1 - t0
        brute_time += t2 - t1
        if not _equal(expected, actual, unordered):
            return {
                "ok": False,
                "stage": "compare",
                "error": "reference and brute force disagree",
                "case_kind": kind,
                "args": _short(args),
                "reference_output": _short(expected),
                "brute_output": _short(actual),
                "cases_run": run,
            }
        run += 1
    return {
        "ok": True,
        "cases_run": run,
        "edge_cases": len(job.get("edge_cases", [])),
        "random_cases": n_random,
        "reference_ms": round(ref_time * 1000, 2),
        "brute_ms": round(brute_time * 1000, 2),
    }


def run(job):
    """Run untrusted student code on inputs and return raw outputs.

    Expected outputs never enter the sandbox. The trusted backend compares, so
    student code can neither read hidden answers nor forge a passing verdict.
    """
    try:
        solution = _load(job["solution"], "solution", "solve")
    except SyntaxError as err:
        return {"status": "compilation_error", "error": "SyntaxError: " + str(err.msg) + " (line " + str(err.lineno) + ")"}
    except Exception as err:
        return {"status": "runtime_error", "error": err.__class__.__name__ + ": " + str(err), "outputs": []}
    outputs = []
    timings = []
    for args in job["inputs"]:
        try:
            t0 = time.perf_counter()
            out = solution(*copy.deepcopy(args))
            timings.append(round((time.perf_counter() - t0) * 1000, 3))
        except MemoryError:
            return {"status": "memory_limit_exceeded", "outputs": outputs, "ms": timings, "failed_index": len(outputs)}
        except RecursionError:
            return {
                "status": "runtime_error",
                "error": "RecursionError: maximum recursion depth exceeded",
                "outputs": outputs,
                "ms": timings,
                "failed_index": len(outputs),
            }
        except Exception as err:
            return {
                "status": "runtime_error",
                "error": err.__class__.__name__ + ": " + str(err),
                "outputs": outputs,
                "ms": timings,
                "failed_index": len(outputs),
            }
        outputs.append(_canon(out, False))
    return {"status": "ok", "outputs": outputs, "ms": timings}


def main():
    job = json.loads(sys.stdin.read())
    sys.setrecursionlimit(10000)
    try:
        if job.get("mode") == "differential":
            result = differential(job)
        elif job.get("mode") == "run":
            result = run(job)
        else:
            result = {"ok": False, "error": "unknown mode"}
    except MemoryError:
        result = {"ok": False, "verdict": "memory_limit_exceeded", "error": "MemoryError"}
    _emit(result)


if __name__ == "__main__":
    main()
