-- Reps core schema: profiles, exam mode, knowledge tracing, coding, XP.
--
-- Access model
--   * The browser (anon key + user JWT) may READ its own rows, and may write only
--     profiles and courses directly.
--   * Everything that decides correctness (questions, keys, attempts, mastery,
--     submissions, XP) is written by the FastAPI backend with the service role,
--     which bypasses RLS. A user can't award themselves XP or mark an answer right
--     by calling the REST API directly.
--   * Answer keys, verification internals, hidden tests and reference solutions
--     live in tables with RLS enabled and NO policies: unreadable from the client.

create extension if not exists pgcrypto;

-- ------------------------------------------------------------------ enums

create type verification_status as enum ('pending', 'verified', 'ai_evaluated', 'rejected', 'unsupported');
create type document_status as enum ('uploaded', 'processing', 'ready', 'failed');
create type job_status as enum ('queued', 'running', 'succeeded', 'failed');
create type question_kind as enum ('multiple_choice', 'numeric', 'symbolic', 'short_answer');
create type session_status as enum ('active', 'completed', 'abandoned');
create type coding_verdict as enum (
  'accepted', 'wrong_answer', 'compilation_error', 'runtime_error',
  'time_limit_exceeded', 'memory_limit_exceeded', 'execution_unavailable', 'pending'
);

-- ------------------------------------------------------------------ profiles

create table profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text check (char_length(display_name) <= 60),
  goals text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create function handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)));
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

-- ------------------------------------------------------------------ courses and material

create table courses (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  code text check (char_length(code) <= 30),
  exam_date date,
  description text check (char_length(description) <= 1000),
  goal text check (char_length(goal) <= 200),
  created_at timestamptz not null default now()
);
create index courses_owner_idx on courses (owner_id);

create table documents (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references courses (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  storage_path text not null unique,
  filename text not null,
  mime_type text not null,
  size_bytes integer not null check (size_bytes > 0),
  page_count integer,
  status document_status not null default 'uploaded',
  error text,
  created_at timestamptz not null default now()
);
create index documents_course_idx on documents (course_id);

create table document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  chunk_index integer not null,
  page_start integer not null,
  page_end integer not null check (page_end >= page_start),
  text text not null,
  unique (document_id, chunk_index)
);

create table processing_jobs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users (id) on delete cascade,
  kind text not null,                       -- 'extract_document', 'generate_questions', ...
  status job_status not null default 'queued',
  idempotency_key text unique,              -- retried enqueues collapse into one job
  attempts integer not null default 0,
  max_attempts integer not null default 3,
  payload jsonb not null default '{}',
  progress jsonb not null default '{}',     -- shown to the user while the job runs
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);
create index processing_jobs_owner_idx on processing_jobs (owner_id, created_at desc);

-- ------------------------------------------------------------------ topics and questions

create table topics (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references courses (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  description text,
  key_concepts text[] not null default '{}',
  source_chunk_ids uuid[] not null default '{}',
  created_at timestamptz not null default now(),
  unique (course_id, name)
);

create table questions (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references courses (id) on delete cascade,
  topic_id uuid not null references topics (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  kind question_kind not null,
  difficulty smallint not null check (difficulty between 1 and 5),
  statement text not null,
  choices jsonb,                            -- multiple choice only
  source_refs jsonb not null default '[]',  -- [{document_id, page, excerpt}]
  verification_status verification_status not null default 'pending',
  prompt_version text not null,
  supersedes uuid references questions (id),
  created_at timestamptz not null default now()
);
create index questions_topic_idx on questions (topic_id) where verification_status in ('verified', 'ai_evaluated');

-- Private: the key and the worked explanation (released by the API after an attempt).
create table question_keys (
  question_id uuid primary key references questions (id) on delete cascade,
  answer text not null,
  task jsonb,                               -- math task spec used for grading
  rubric jsonb,                             -- conceptual questions
  explanation text not null
);

-- Private: every verification run, kept for the capstone audit.
create table question_verifications (
  id uuid primary key default gen_random_uuid(),
  question_id uuid not null references questions (id) on delete cascade,
  status verification_status not null,
  method text not null,
  checks jsonb not null default '[]',
  reason text,
  duration_ms integer not null,
  created_at timestamptz not null default now()
);

-- Only the backend moves a question between states, and only along legal edges.
create function enforce_verification_transition() returns trigger
language plpgsql as $$
begin
  if old.verification_status <> new.verification_status and old.verification_status <> 'pending' then
    raise exception 'verification status % is final', old.verification_status;
  end if;
  return new;
end;
$$;

create trigger questions_verification_transition
  before update of verification_status on questions
  for each row execute function enforce_verification_transition();

-- ------------------------------------------------------------------ boss fights

create table exam_sessions (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references courses (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  status session_status not null default 'active',
  boss_name text not null,
  hp_start smallint not null check (hp_start between 0 and 100),
  hp_current smallint not null check (hp_current between 0 and 100),
  question_target smallint not null default 15,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);
create index exam_sessions_owner_idx on exam_sessions (owner_id, started_at desc);

create table exam_attempts (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references exam_sessions (id) on delete cascade,
  question_id uuid not null references questions (id) on delete cascade,
  owner_id uuid not null references auth.users (id) on delete cascade,
  answer text not null check (char_length(answer) <= 2000),
  correct boolean,                           -- null when the answer couldn't be graded
  grading_method text not null,
  grading_category verification_status not null,  -- 'verified' or 'ai_evaluated'
  hp_before smallint not null,
  hp_after smallint not null,
  idempotency_key text not null unique,      -- a retried submit can't double-count
  created_at timestamptz not null default now()
);
create index exam_attempts_session_idx on exam_attempts (session_id, created_at);

-- ------------------------------------------------------------------ knowledge tracing

create table topic_mastery (
  owner_id uuid not null references auth.users (id) on delete cascade,
  topic_id uuid not null references topics (id) on delete cascade,
  p_known double precision not null check (p_known between 0 and 1),
  attempts integer not null default 0,
  correct integer not null default 0 check (correct <= attempts),
  model_version text not null,
  updated_at timestamptz not null default now(),
  primary key (owner_id, topic_id)
);

create table mastery_events (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users (id) on delete cascade,
  topic_id uuid not null references topics (id) on delete cascade,
  attempt_id uuid references exam_attempts (id) on delete set null,
  p_before double precision not null,
  p_after double precision not null,
  correct boolean not null,
  difficulty smallint,
  model_version text not null,
  created_at timestamptz not null default now()
);

-- ------------------------------------------------------------------ coding arena

create table coding_problems (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  title text not null,
  pattern text not null,
  difficulty text not null check (difficulty in ('easy', 'medium', 'hard')),
  statement text not null,
  signature text not null,
  public_examples jsonb not null default '[]',   -- [{args, expected}]
  unordered_output boolean not null default false,
  verification_status verification_status not null default 'pending',
  created_at timestamptz not null default now()
);

-- Private
create table coding_problem_sources (
  problem_id uuid primary key references coding_problems (id) on delete cascade,
  reference_solution text not null,
  brute_force_solution text not null,
  generator text not null,
  verification jsonb not null                   -- seed, cases run, timings
);

-- Private
create table coding_test_cases (
  id uuid primary key default gen_random_uuid(),
  problem_id uuid not null references coding_problems (id) on delete cascade,
  ordinal integer not null,
  args jsonb not null,
  expected jsonb not null,
  hidden boolean not null,
  unique (problem_id, ordinal)
);

create table coding_submissions (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users (id) on delete cascade,
  problem_id uuid not null references coding_problems (id) on delete cascade,
  language text not null default 'python',
  code text not null check (char_length(code) <= 50000),
  is_submit boolean not null,                   -- false = "Run" on public tests only
  verdict coding_verdict not null default 'pending',
  passed integer,
  total integer,
  runtime_ms double precision,
  executor text,
  created_at timestamptz not null default now()
);
create index coding_submissions_owner_idx on coding_submissions (owner_id, problem_id, created_at desc);

-- ------------------------------------------------------------------ XP

create table xp_events (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users (id) on delete cascade,
  reason text not null,                         -- 'exam_correct', 'coding_accepted', ...
  amount integer not null check (amount > 0),
  source_type text not null,
  source_id uuid not null,
  created_at timestamptz not null default now(),
  unique (owner_id, reason, source_type, source_id)  -- one award per event
);
create index xp_events_owner_idx on xp_events (owner_id, created_at desc);

-- ------------------------------------------------------------------ row level security

alter table profiles enable row level security;
alter table courses enable row level security;
alter table documents enable row level security;
alter table document_chunks enable row level security;
alter table processing_jobs enable row level security;
alter table topics enable row level security;
alter table questions enable row level security;
alter table question_keys enable row level security;
alter table question_verifications enable row level security;
alter table exam_sessions enable row level security;
alter table exam_attempts enable row level security;
alter table topic_mastery enable row level security;
alter table mastery_events enable row level security;
alter table coding_problems enable row level security;
alter table coding_problem_sources enable row level security;
alter table coding_test_cases enable row level security;
alter table coding_submissions enable row level security;
alter table xp_events enable row level security;

create policy "own profile: read" on profiles for select to authenticated using (id = auth.uid());
create policy "own profile: update" on profiles for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

create policy "own courses: read" on courses for select to authenticated using (owner_id = auth.uid());
create policy "own courses: insert" on courses for insert to authenticated with check (owner_id = auth.uid());
create policy "own courses: update" on courses for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "own courses: delete" on courses for delete to authenticated using (owner_id = auth.uid());

create policy "own rows: read" on documents for select to authenticated using (owner_id = auth.uid());
create policy "own rows: read" on document_chunks for select to authenticated using (owner_id = auth.uid());
create policy "own rows: read" on processing_jobs for select to authenticated using (owner_id = auth.uid());
create policy "own rows: read" on topics for select to authenticated using (owner_id = auth.uid());
create policy "own published questions: read" on questions for select to authenticated
  using (owner_id = auth.uid() and verification_status in ('verified', 'ai_evaluated'));
create policy "own rows: read" on exam_sessions for select to authenticated using (owner_id = auth.uid());
create policy "own rows: read" on exam_attempts for select to authenticated using (owner_id = auth.uid());
create policy "own rows: read" on topic_mastery for select to authenticated using (owner_id = auth.uid());
create policy "own rows: read" on mastery_events for select to authenticated using (owner_id = auth.uid());
create policy "own rows: read" on coding_submissions for select to authenticated using (owner_id = auth.uid());
create policy "own rows: read" on xp_events for select to authenticated using (owner_id = auth.uid());

create policy "verified problems: read" on coding_problems for select to authenticated
  using (verification_status = 'verified');

-- question_keys, question_verifications, coding_problem_sources, coding_test_cases:
-- RLS on, no policies. Only the service role (backend) can touch them.

-- ------------------------------------------------------------------ views for the dashboard

create view player_summary with (security_invoker = true) as
select
  p.id as owner_id,
  p.display_name,
  coalesce((select sum(amount) from xp_events x where x.owner_id = p.id), 0)::integer as xp,
  (select count(*) from exam_sessions s where s.owner_id = p.id and s.status = 'completed')::integer as exams_completed,
  (select count(distinct problem_id) from coding_submissions c
     where c.owner_id = p.id and c.is_submit and c.verdict = 'accepted')::integer as problems_solved
from profiles p;
