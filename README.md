# Reps

One training ground for college students: fight bosses built from your courses, solve coding problems in the Arena, and run mock interviews in the Gauntlet. KTP technical capstone, CS / ITI track.

Wherever an answer can be checked by running something, Reps checks it that way. The AI explains results; it doesn't decide them.

![Boss fight](docs/screenshots/05-fight-hit.png)

## Run it

**Windows:** install [Python 3.11+](https://www.python.org/downloads/) (tick "Add to PATH") and [Node.js 20+](https://nodejs.org/), then double-click `start-reps.bat`. The first run installs everything; after that it opens two windows (API and web) and your browser at http://localhost:3000.

**macOS / Linux:** `./start-reps.sh`

Use Chrome or Edge for voice interviews. Everything else works in any modern browser. Progress is saved locally in `apps/api/data/reps.db`.

Optional: copy `.env.example` to `.env` and set `LLM_API_KEY` and `LLM_MODEL` to turn on question generation from your own PDFs and AI STAR scoring in interviews.

## The three modes

| Mode | What you do | What's checked, and how |
| --- | --- | --- |
| Boss fights | Answer questions; correct answers damage the boss, wrong ones cost a heart | Every answer key is computed twice (SymPy symbolic and mpmath numeric) before you see the question; your answer is checked by symbolic equivalence |
| Arena | Solve original Python problems by pattern | Your code runs against public and hidden tests; each problem passed reference vs brute-force checks on 300+ random inputs before publishing |
| Gauntlet | Answer behavioral, resume, and coding questions out loud or typed | Pace and pauses measured from microphone audio levels; filler words and structure counted from the transcript; code run against tests; STAR scores only with an AI key, labeled as AI judgment |

### Game rules

- **Boss HP** = 100 × (1 − average mastery) across the course's topics. The HP bar has one segment per topic, so the long red segments are your weak topics.
- **Mastery** is a Bayesian Knowledge Tracing estimate per topic, updated after every graded answer and kept between fights.
- **Win** by getting the boss to 25 HP or less (75% average mastery). **Lose** if your 5 hearts run out. A fight is at most 15 questions.
- **Targeting:** the boss asks every topic once, then mostly attacks your weakest topic, but never the same one more than twice in a row. Question difficulty follows your mastery.
- **Phase 2** starts when the boss drops to 50 HP: questions get one step harder. Each built-in boss also has an ability (a miss on its signature topic costs 2 hearts).
- **Rematch:** a question you miss comes back two questions later with new numbers.
- **Show your work:** turn it on and type one step per line. Every line is checked, and the first wrong line is flagged with what went wrong (sign slip, dropped factor, lost solution).
- **Forgetting:** mastery fades between sessions on a half-life that grows each time you get a topic right. The **Daily Raid** is 5 questions on whatever is fading most, 3 hearts, cleared with 3 right.
- **XP** comes only from confirmed events (verified correct answers, accepted solutions, finished sessions) and each event pays once. XP is motivation, not a grade. 20 achievements sit on top of it.

### Arena speed tiers

An accepted solution is also timed on an input 100 to 1,000 times larger, generated inside the sandbox. It clears the speed tier if it runs within 20× the reference solution's time on the same machine, which separates an O(n log n) answer from an O(n²) one.

### Party raids

Up to 8 players on the same Wi-Fi fight one boss over a WebSocket. The host opens a room and gets a four-letter code; friends open the link the lobby shows (or type the code on the Party page). Everyone gets their own verified questions, and every correct answer from anyone hits one shared HP bar (20 + 60 per player). Damage is 8, 11 or 14 by difficulty plus a streak bonus, everyone has 3 hearts, a 3-answer streak revives a downed teammate, and the clock runs 6 minutes. Answers are graded on the server, never trusted from the browser. In local mode the host's answers count toward mastery and XP; guests play for the leaderboard.

![Party raid](docs/screenshots/15-party-raid.png)

### Progress

Mastery over time for every topic, XP by day, accuracy by course, the verification record (how many generated questions and problems were checked, and how many were thrown out and why), and the achievements grid.

![Mastery over time](docs/screenshots/17-progress-mastery.png)

## Architecture

```mermaid
flowchart LR
  browser[Next.js app] -->|/api, WebSocket| api[FastAPI]
  api --> store[(SQLite, local mode)]
  api --> pool[Verification workers<br/>SymPy + mpmath]
  api --> runner[Code runner<br/>local or Judge0]
  api --> bkt[Knowledge tracing]
  api --> rooms[Party rooms<br/>in memory]
  api -.optional.-> llm[LLM API]
  browser --> mic[Mic + Web Audio<br/>Speech API]
```

The hosted version swaps SQLite for Supabase: the schema and row level security policies are in `supabase/migrations` and tested in CI.

## Components (track requirements)

| Component | Category | Where |
| --- | --- | --- |
| PDF parsing into page-cited chunks, resume claim extraction | File processing | `reps_api/ingest`, `reps_api/interview.py` |
| Question generation from your notes, AI STAR scoring | AI / NLP | `reps_api/generation.py`, `reps_api/llm.py` |
| Answer-key verification, differential testing, code execution | Algorithm + external API | `reps_api/verification` |
| Bayesian Knowledge Tracing and the boss policy | Machine learning | `reps_api/tutor`, `eval/assistments_bkt.py` |
| Live voice: transcript, audio-level pause detection, spoken questions | Real-time | `apps/web/lib/voice.ts` |
| Party raids: shared boss state pushed to every player over WebSockets | Real-time | `reps_api/party.py`, `apps/web/lib/party.ts` |
| Course generation jobs with persisted progress | Background jobs | `reps_api/generation.py` |

## Design tools

`.claude/agents/` holds four design-review subagents (micro-interactions, ARIA, mobile-first layout, mobile design) used to audit Reps' motion, accessibility and phone layout. They're adapted from [claude-code-ui-agents](https://github.com/mustafakendiguzel/claude-code-ui-agents) by Mustafa Kendigüzel (MIT, license included in that folder), with Reps-specific context added.

## Tests

```bash
cd apps/api && pytest -q                                  # 142 backend tests
python eval/assistments_bkt.py --synthetic                # BKT evaluation pipeline self-check
cd ../web && npm run typecheck && npm run build
REPS_DB_PATH=../api/data/reps.db python e2e/playthrough.py   # browser playthrough of all three modes
python e2e/party.py                                        # two-player party raid (stop the API first; this runs its own)
```

The database tests run the Supabase migration on plain Postgres with row level security checks (see `.github/workflows/ci.yml`).

## Known limitations

- **Local runner isn't a sandbox.** On Linux/macOS it limits CPU and memory; on Windows only time. It doesn't block network access. Production must use Judge0 (`JUDGE0_URL`), and the API refuses the local runner when `REPS_ENV=production`.
- **Windows support is written but tested only on Linux so far.** The Windows-specific code path (no resource limits) is covered by a test that forces it.
- **Voice** depends on the browser's speech recognition (Chrome, Edge). It often drops "um" and "uh", so filler counts run low. Pause and pace numbers come from audio levels and don't depend on it. Voice hasn't been tested automatically; the e2e test types its answers.
- **Built-in courses** cover Calculus I and kinematics. Your own courses need an AI key, and only computational questions are generated so far.
- **Resume claims** are found with simple rules (bullets and numbers), not AI.
- **BKT parameters** are defaults; the ASSISTments evaluation hasn't been run on real data yet.
- **No login** in local mode, so everything is saved for one person: the person running Reps. Party raid guests don't get saved progress, and party rooms live in memory, so restarting the API ends any open raid.
- **Party raids need port 3000 reachable** on the host's network. Windows may ask to allow Node.js through the firewall the first time; allow it on private networks. School and public Wi-Fi often block device-to-device traffic, so a phone hotspot is the fallback.

## Next

Supabase login with per-user progress (party raid guests keep their own XP), hosting (Vercel for the web app, Render for the API), Judge0, conceptual questions with rubric grading, more Arena problems and languages.
