"use client";

import { Check, Code2, Mic, Pencil, Play, Swords } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BossArt } from "@/components/BossArt";
import { MasteryBar, SegmentedHp } from "@/components/Hud";
import { ErrorNote, Spinner, Stat, XP_REASON, timeAgo } from "@/components/ui";
import { api, notifyProgress, type Course, type InterviewHistoryItem, type Player, type ProblemSummary } from "@/lib/api";

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Late session" : h < 12 ? "Morning" : h < 18 ? "Afternoon" : "Evening";
}

function NameEditor({ player, onSaved }: { player: Player; onSaved: (p: Player) => void }) {
  const [editing, setEditing] = useState(player.name === "Player");
  const [name, setName] = useState(player.name === "Player" ? "" : player.name);
  if (!editing)
    return (
      <button type="button" onClick={() => setEditing(true)} className="ml-2 inline-flex text-muted hover:text-text" aria-label="Change your name">
        <Pencil size={16} />
      </button>
    );
  return (
    <form
      className="mt-3 flex max-w-sm gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!name.trim()) return;
        onSaved(await api.rename(name.trim()));
        setEditing(false);
        notifyProgress();
      }}
    >
      <label htmlFor="name" className="sr-only">
        Your name
      </label>
      <input id="name" className="field" placeholder="What should Reps call you?" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      <button className="btn-primary" type="submit">
        Save
      </button>
    </form>
  );
}

export default function Hub() {
  const [player, setPlayer] = useState<Player | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [problems, setProblems] = useState<ProblemSummary[]>([]);
  const [interviews, setInterviews] = useState<InterviewHistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [p, c, pr, iv] = await Promise.all([api.player(), api.courses(), api.problems(), api.interviews()]);
      setPlayer(p);
      setCourses(c);
      setProblems(pr);
      setInterviews(iv);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <ErrorNote message={error} onRetry={load} />;
  if (!player) return <Spinner label="Loading your hub" />;

  const solved = problems.filter((p) => p.status === "solved").length;
  const featured = [...courses].sort((a, b) => (b.active_session_id ? 1 : 0) - (a.active_session_id ? 1 : 0) || a.hp - b.hp)[0];
  const fresh = player.stats.questions_answered === 0 && solved === 0 && player.stats.interviews === 0;
  const doneInterviews = interviews.filter((i) => i.status === "completed").length;

  return (
    <div className="space-y-10">
      <section className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="h-display text-4xl md:text-5xl">
            {greeting()}
            {player.name !== "Player" ? `, ${player.name}` : ""}.
            {player.name !== "Player" && <NameEditor player={player} onSaved={setPlayer} />}
          </h1>
          {player.name === "Player" && <NameEditor player={player} onSaved={setPlayer} />}
          <p className="mt-2 max-w-xl text-muted">
            {fresh
              ? "Start with a boss fight. Every answer is checked by math, not guessed by AI, and your weak spots show up as you play."
              : player.practiced_today
                ? "You've trained today. One more round keeps the weak spots shrinking."
                : "Pick up where you left off, or hit your weakest topic first."}
          </p>
        </div>
        <div className="flex gap-10">
          <Stat value={player.stats.bosses_defeated} label="Bosses beaten" />
          <Stat value={`${solved}/${problems.length}`} label="Problems solved" tone="cyan" />
          <Stat value={player.best_streak} label="Best streak" tone="xp" />
        </div>
      </section>

      {/* The three modes */}
      <section aria-labelledby="modes" className="grid gap-4 lg:grid-cols-[1.35fr_1fr_1fr]">
        <h2 id="modes" className="sr-only">
          Training modes
        </h2>
        <Link
          href={featured?.active_session_id ? `/exam/${featured.active_session_id}` : "/exam"}
          className="group relative overflow-hidden rounded-panel border border-line bg-gradient-to-br from-[#241944] to-surface p-6 transition hover:border-violet/70"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 font-display text-sm font-semibold text-violet-soft">
                <Swords size={16} aria-hidden /> Boss fights
              </div>
              <h3 className="h-display mt-2 text-2xl">{featured ? featured.boss_name : "Exam bosses"}</h3>
              <p className="mt-1 text-sm text-muted">
                {featured ? `${featured.name}${featured.active_session_id ? ", fight in progress" : ""}` : "Your syllabus becomes the boss."}
              </p>
            </div>
            {featured && <BossArt courseId={featured.id} name={featured.boss_name} className="-mr-2 -mt-2 h-28 w-28 shrink-0" />}
          </div>
          {featured && (
            <div className="mt-5">
              <SegmentedHp topics={featured.topics} hp={featured.hp} compact />
            </div>
          )}
          <span className="btn-primary mt-5">
            <Play size={16} aria-hidden /> {featured?.active_session_id ? "Resume the fight" : "Choose a boss"}
          </span>
        </Link>

        <Link href="/arena" className="group rounded-panel border border-line bg-gradient-to-br from-[#10303A] to-surface p-6 transition hover:border-cyan/70">
          <div className="flex items-center gap-2 font-display text-sm font-semibold text-cyan">
            <Code2 size={16} aria-hidden /> Arena
          </div>
          <h3 className="h-display mt-2 text-2xl">Coding patterns</h3>
          <p className="mt-1 text-sm text-muted">Original problems, graded by running your code against hidden tests.</p>
          <div className="mt-5 grid grid-cols-6 gap-1.5" aria-label={`${solved} of ${problems.length} solved`}>
            {problems.map((p) => (
              <div
                key={p.slug}
                title={`${p.title}: ${p.status}`}
                className={`flex h-9 items-center justify-center rounded-md border ${
                  p.status === "solved" ? "border-cyan bg-cyan/20 text-cyan" : p.status === "attempted" ? "border-cyan/40 bg-raised" : "border-line bg-ink/50"
                }`}
              >
                {p.status === "solved" && <Check size={16} aria-hidden />}
              </div>
            ))}
          </div>
          <span className="btn-cyan mt-5">Enter the Arena</span>
        </Link>

        <Link href="/interview" className="group rounded-panel border border-line bg-gradient-to-br from-[#3A2A10] to-surface p-6 transition hover:border-xp/70">
          <div className="flex items-center gap-2 font-display text-sm font-semibold text-xp">
            <Mic size={16} aria-hidden /> Gauntlet
          </div>
          <h3 className="h-display mt-2 text-2xl">Mock interviews</h3>
          <p className="mt-1 text-sm text-muted">Answer out loud. Reps measures your pace and pauses and presses on your resume.</p>
          <div className="mt-5 font-display text-sm text-muted">
            <span className="text-3xl font-bold text-text">{doneInterviews}</span> finished
          </div>
          <span className="btn mt-5 bg-xp text-ink hover:bg-[#ffd47a]">Start an interview</span>
        </Link>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        <div className="panel p-6">
          <h2 className="h-display text-xl">Weak spots</h2>
          <p className="mt-1 text-sm text-muted">Lowest mastery first, from your actual answers. Faded bars have fewer than 3 answers behind them.</p>
          {player.weak_topics.length === 0 ? (
            <p className="mt-6 text-muted">Nothing yet. Your first fight maps where you stand.</p>
          ) : (
            <ul className="mt-5 space-y-4">
              {player.weak_topics.map((t) => (
                <li key={t.id} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1">
                  <div>
                    <span className="font-medium">{t.name}</span>
                    <span className="ml-2 text-sm text-muted">{t.course}</span>
                    {t.provisional && <span className="chip ml-2">{t.attempts} answered</span>}
                  </div>
                  <Link href="/exam" className="text-sm font-semibold text-violet-soft hover:underline">
                    Train
                  </Link>
                  <div className="col-span-2">
                    <MasteryBar value={t.mastery} provisional={t.provisional} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-6">
          <div className="panel p-6">
            <h2 className="h-display text-xl">Continue</h2>
            <ul className="mt-4 space-y-2 text-sm">
              {player.continue.exam && (
                <li>
                  <Link className="flex justify-between rounded-chip bg-raised px-3 py-2.5 hover:bg-line" href={`/exam/${player.continue.exam.id}`}>
                    <span>Fight {player.continue.exam.boss_name}</span>
                    <span className="text-hp">{player.continue.exam.hp_current} HP</span>
                  </Link>
                </li>
              )}
              {player.continue.coding && (
                <li>
                  <Link className="flex justify-between rounded-chip bg-raised px-3 py-2.5 hover:bg-line" href={`/arena/${player.continue.coding.slug}`}>
                    <span>{problems.find((p) => p.slug === player.continue.coding?.slug)?.title ?? "Unsolved problem"}</span>
                    <span className="text-muted">{timeAgo(player.continue.coding.last)}</span>
                  </Link>
                </li>
              )}
              {player.continue.interview && (
                <li>
                  <Link className="flex justify-between rounded-chip bg-raised px-3 py-2.5 hover:bg-line" href={`/interview/${player.continue.interview.id}`}>
                    <span>Unfinished interview</span>
                    <span className="text-muted">{timeAgo(player.continue.interview.started_at)}</span>
                  </Link>
                </li>
              )}
              {!player.continue.exam && !player.continue.coding && !player.continue.interview && (
                <li className="text-muted">Nothing in progress. Start any mode above.</li>
              )}
            </ul>
          </div>
          <div className="panel p-6">
            <h2 className="h-display text-xl">Recent XP</h2>
            {player.recent_xp.length === 0 ? (
              <p className="mt-3 text-sm text-muted">{player.xp_rules}</p>
            ) : (
              <ul className="mt-3 divide-y divide-line text-sm">
                {player.recent_xp.map((x, i) => (
                  <li key={i} className="flex justify-between py-2">
                    <span>{XP_REASON[x.reason] ?? x.reason}</span>
                    <span className="font-display font-semibold tabular-nums text-xp">+{x.amount}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
