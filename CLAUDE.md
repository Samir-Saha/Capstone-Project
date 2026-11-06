# Reps

Gamified study app (KTP technical capstone). Three modes:
- Boss fights: exam practice built from class notes, mastery tracked with Bayesian Knowledge Tracing plus forgetting.
- Arena: coding problems graded by hidden tests.
- Gauntlet: voice mock interviews built from a resume.

## Layout
- `apps/api` — FastAPI on Python 3.11+, SQLite at `apps/api/data/reps.db`. Entry: `reps_api.main:app`.
  - `reps_api/exam.py` boss fights and mastery, `progress.py` Progress page data, `interview.py` Gauntlet, `content/seed_coding.py` Arena problems.
- `apps/web` — Next.js 15, React 19, TypeScript, Tailwind 3. API client and types in `lib/api.ts`.
  - Colors are CSS-variable RGB tokens in `tailwind.config.ts` (`hp`, `heal`, `xp`, `sun`, `violet`, `cyan`, `line`, `muted`). Don't invent class names like `bg-boss`.

## Commands (Windows, from the repo root)
- Run everything: `.\start-reps.bat` (API on :8000, web on :3000).
- API tests: `cd apps\api; .venv\Scripts\python -m pytest -q`
- Lint: `cd apps\api; .venv\Scripts\ruff check .`
- Web typecheck: `cd apps\web; npx tsc --noEmit`
- Web build: `cd apps\web; npx next build`

Run pytest, ruff and tsc before calling a change done.

## Rules
- Every Arena problem is a `CodingProblemSpec` that must pass `verify_coding_problem` (reference vs brute force on random inputs, plus a `scale_generator` for the speed tier). If you add a problem, update the count assertion in `tests/test_api.py`.
- Never invent metrics or features in copy. Label status honestly: built, not yet configured (Judge0, LLM key), or planned.
- `.env` holds `LLM_API_KEY` / `LLM_MODEL`. Never commit `.env` and never put a real key in `.env.example`.
- Don't create or restore Supabase projects without asking.
- Commits are authored as Samir Saha <samirsaha0613@gmail.com>, with no Co-Authored-By or session trailers.
