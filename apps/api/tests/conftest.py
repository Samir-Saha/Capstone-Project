import os

import pytest

os.environ.setdefault("REPS_SKIP_WARMUP", "1")
os.environ.pop("LLM_API_KEY", None)
os.environ.pop("JUDGE0_URL", None)

from reps_api import exam  # noqa: E402
from reps_api.store import Store, set_store  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "reps.db")
    exam.sync_builtin_courses(s)
    set_store(s)
    yield s
    set_store(None)
    s.close()
