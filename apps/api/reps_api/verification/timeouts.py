"""Run CPU-heavy functions in worker processes with a hard wall-clock limit.

SymPy can run for minutes on adversarial input (huge simplifications, integrals with
no closed form). A thread can't be killed; a process can.

Works on Windows, macOS and Linux: a small pool of warm worker processes (SymPy
already imported) handles jobs. When a job overruns, the whole pool is killed and
rebuilt, which is rare and costs about a second.
"""

from __future__ import annotations

import multiprocessing as mp
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

# forkserver where available (POSIX): forking a threaded API process can deadlock.
# Windows only has spawn.
_METHOD = "spawn" if sys.platform == "win32" else "forkserver"
_WORKERS = 2


class VerificationTimeout(TimeoutError):
    pass


def _warm() -> None:
    import mpmath  # noqa: F401
    import sympy  # noqa: F401

    from . import math_engine  # noqa: F401


class _Pool:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pool: ProcessPoolExecutor | None = None

    def _get(self) -> ProcessPoolExecutor:
        with self._lock:
            if self._pool is None:
                self._pool = ProcessPoolExecutor(max_workers=_WORKERS, mp_context=mp.get_context(_METHOD), initializer=_warm)
            return self._pool

    def _reset(self, broken: ProcessPoolExecutor) -> None:
        with self._lock:
            if self._pool is not broken:
                return
            for proc in list(getattr(broken, "_processes", {}).values()):
                proc.kill()
            broken.shutdown(wait=False, cancel_futures=True)
            self._pool = None

    def run(self, fn: Callable[..., Any], args: tuple, kwargs: dict, timeout_s: float) -> Any:
        pool = self._get()
        future = pool.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout_s)
        except FutureTimeout as err:
            self._reset(pool)
            raise VerificationTimeout(f"exceeded {timeout_s:.0f}s") from err

    def shutdown(self) -> None:
        with self._lock:
            if self._pool is not None:
                self._pool.shutdown(wait=False, cancel_futures=True)
                self._pool = None


_POOL = _Pool()


def run_with_timeout(fn: Callable[..., Any], *args: Any, timeout_s: float = 15.0, **kwargs: Any) -> Any:
    """Run fn(*args, **kwargs) in a worker process. fn must be importable (module level)."""
    return _POOL.run(fn, args, kwargs, timeout_s)


def shutdown_pool() -> None:
    _POOL.shutdown()
