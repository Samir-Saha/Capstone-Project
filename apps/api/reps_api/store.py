"""Local persistence (SQLite) for running Reps on one computer.

This is the "local mode" store: one player, progress saved in apps/api/data/reps.db.
The Supabase schema in supabase/migrations mirrors these tables with per-user
ownership and row level security for the hosted version.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
create table if not exists player (
  id integer primary key check (id = 1),
  display_name text not null default 'Player',
  created_at text not null
);

create table if not exists xp_events (
  id text primary key,
  reason text not null,
  amount integer not null check (amount > 0),
  source_type text not null,
  source_id text not null,
  created_at text not null,
  local_day text not null,
  unique (reason, source_type, source_id)
);

create table if not exists courses (
  id text primary key,
  name text not null,
  code text,
  boss_name text not null,
  kind text not null check (kind in ('builtin', 'uploaded')),
  exam_date text,
  created_at text not null
);

create table if not exists topics (
  id text primary key,
  course_id text not null references courses (id) on delete cascade,
  name text not null,
  description text,
  position integer not null default 0
);

create table if not exists templates (
  id text primary key,
  course_id text not null references courses (id) on delete cascade,
  topic_id text not null references topics (id) on delete cascade,
  difficulty integer not null,
  body text not null,           -- JSON QuestionTemplate
  source text                   -- JSON source reference (uploaded courses)
);

create table if not exists documents (
  id text primary key,
  course_id text references courses (id) on delete cascade,
  filename text not null,
  page_count integer,
  char_count integer,
  status text not null,
  error text,
  created_at text not null
);

create table if not exists jobs (
  id text primary key,
  kind text not null,
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed')),
  progress text not null default '{}',
  error text,
  result text,
  created_at text not null,
  finished_at text
);

create table if not exists topic_mastery (
  topic_id text primary key references topics (id) on delete cascade,
  p_known real not null check (p_known between 0 and 1),
  attempts integer not null default 0,
  correct integer not null default 0,
  model_version text not null,
  updated_at text not null
);

create table if not exists mastery_events (
  id text primary key,
  topic_id text not null,
  attempt_id text,
  p_before real not null,
  p_after real not null,
  correct integer not null,
  difficulty integer,
  model_version text not null,
  created_at text not null
);

create table if not exists exam_sessions (
  id text primary key,
  course_id text not null references courses (id) on delete cascade,
  status text not null check (status in ('active', 'completed', 'abandoned')),
  outcome text check (outcome in ('victory', 'knocked_out', 'out_of_questions', 'retreated')),
  boss_name text not null,
  hp_start integer not null,
  hp_current integer not null,
  hearts integer not null,
  combo integer not null default 0,
  best_combo integer not null default 0,
  question_target integer not null,
  mastery_start text not null default '{}',
  started_at text not null,
  completed_at text
);

create table if not exists exam_questions (
  id text primary key,
  session_id text not null references exam_sessions (id) on delete cascade,
  topic_id text not null,
  template_id text not null,
  seed integer not null,
  difficulty integer not null,
  prompt text not null,
  latex text,
  task text not null,             -- JSON MathTask
  answer text not null,           -- verified key: never sent before the attempt
  answer_latex text,
  rel_tol real,
  hint text,
  method text,
  answer_format text,
  verification text not null,     -- JSON checks
  hint_used integer not null default 0,
  created_at text not null
);

create table if not exists exam_attempts (
  id text primary key,
  session_id text not null,
  question_id text not null unique references exam_questions (id) on delete cascade,
  answer text not null,
  correct integer not null,
  method text not null,
  hp_before integer not null,
  hp_after integer not null,
  p_before real not null,
  p_after real not null,
  xp integer not null default 0,
  created_at text not null
);

create table if not exists verification_log (
  id text primary key,
  subject text not null,          -- 'math_template' | 'coding_problem'
  subject_id text not null,
  status text not null,
  reason text,
  method text,
  duration_ms integer,
  created_at text not null
);

create table if not exists coding_submissions (
  id text primary key,
  slug text not null,
  code text not null,
  is_submit integer not null,
  verdict text not null,
  passed integer,
  total integer,
  runtime_ms real,
  executor text,
  created_at text not null
);
create index if not exists coding_submissions_slug on coding_submissions (slug, created_at);

create table if not exists resumes (
  id text primary key,
  filename text not null,
  text text not null,
  claims text not null,
  extraction text not null,
  created_at text not null
);

create table if not exists interview_sessions (
  id text primary key,
  role text not null,
  kind text not null,
  resume_id text references resumes (id) on delete set null,
  plan text not null,             -- JSON list of planned questions
  status text not null check (status in ('active', 'completed')),
  started_at text not null,
  completed_at text
);

create table if not exists interview_turns (
  id text primary key,
  session_id text not null references interview_sessions (id) on delete cascade,
  idx integer not null,
  question text not null,
  question_source text not null,
  answer text not null,
  input_mode text not null,
  metrics text not null,
  checks text not null,
  ai_feedback text,
  created_at text not null,
  unique (session_id, idx)
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def local_day() -> str:
    return datetime.now().astimezone().date().isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def default_path() -> Path:
    env = os.environ.get("REPS_DB_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "data" / "reps.db"


class Store:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("pragma foreign_keys = on")
        self._conn.execute("pragma journal_mode = wal")
        self._lock = threading.RLock()
        self._conn.executescript(SCHEMA)
        self._conn.execute("insert or ignore into player (id, created_at) values (1, ?)", (now_iso(),))

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("begin immediate")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("rollback")
                raise
            self._conn.execute("commit")

    def one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def run(self, sql: str, params: tuple | dict = ()) -> int:
        with self._lock:
            return self._conn.execute(sql, params).rowcount

    def close(self) -> None:
        self._conn.close()


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def loads(text: str | None) -> Any:
    return json.loads(text) if text else None


_STORE: Store | None = None
_STORE_LOCK = threading.Lock()


def get_store() -> Store:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = Store()
        return _STORE


def set_store(store: Store | None) -> None:
    """Tests swap in a temporary database."""
    global _STORE
    with _STORE_LOCK:
        _STORE = store
