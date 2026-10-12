"""Run a CPU-heavy function in a child process with a hard wall-clock limit.

SymPy can run for minutes on adversarial input (huge simplifications, integrals with
no closed form). A thread can't be killed; a process can.
"""

from __future__ import annotations

import multiprocessing as mp
from collections.abc import Callable
from typing import Any

# forkserver, not fork: the API process runs threads, and forking a threaded
# process can deadlock the child. The server preloads SymPy once, so each job
# still starts fast.
_CTX = mp.get_context("forkserver")
_CTX.set_forkserver_preload(["sympy", "mpmath", "reps_api.verification.math_engine"])


class VerificationTimeout(TimeoutError):
    pass


def _child(conn, fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
    try:
        conn.send(("ok", fn(*args, **kwargs)))
    except BaseException as err:  # report everything, including SystemExit
        conn.send(("error", f"{err.__class__.__name__}: {err}"))
    finally:
        conn.close()


def run_with_timeout(fn: Callable[..., Any], *args: Any, timeout_s: float = 15.0, **kwargs: Any) -> Any:
    parent, child = _CTX.Pipe(duplex=False)
    proc = _CTX.Process(target=_child, args=(child, fn, args, kwargs), daemon=True)
    proc.start()
    child.close()
    if not parent.poll(timeout_s):
        proc.kill()
        proc.join()
        raise VerificationTimeout(f"exceeded {timeout_s:.0f}s")
    kind, payload = parent.recv()
    proc.join()
    if kind == "error":
        raise RuntimeError(payload)
    return payload
