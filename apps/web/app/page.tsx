"use client";

import { Code2, Flame, Mic, Pencil, Play, Star, Swords, Trophy, Users, Zap } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BossArt } from "@/components/BossArt";
import { RaidCard } from "@/components/RaidCard";
import { MasteryBar } from "@/components/Hud";
import { QuestBanner } from "@/components/PixelScene";
import { Ring } from "@/components/Ring";
import { CountStat, ErrorNote, Spinner, XP_REASON, timeAgo } from "@/components/ui";
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

  const allTopics = courses.flatMap((c) => c.topics);
  const tried = allTopics.filter((t) => t.attempts > 0);
  const studyMastery = tried.length ? tried.reduce((a, t) => a + t.mastery, 0) / tried.length : null;
  const beaten = courses.filter((c) => c.victories > 0).length;
  const lastInterview = interviews.find((i) => i.status === "completed");
  const xpIcon = (reason: string) =>
    reason.startsWith("coding") ? (
      <Code2 size={16} className="text-cyan" aria-hidden />
    ) : reason.startsWith("interview") ? (
      <Mic size={16} className="text-heal" aria-hidden />
    ) : reason.startsWith("party") ? (
      <Users size={16} className="text-cyan" aria-hidden />
    ) : (
      <Swords size={16} className="text-violet-soft" aria-hidden />
    );

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="h-display text-4xl md:text-5xl">
            {player.name !== "Player" ? `Welcome back, ${player.name}!` : `${greeting()}.`}
            {player.name !== "Player" && <NameEditor player={player} onSaved={setPlayer} />}
          </h1>
          {player.name === "Player" && <NameEditor player={player} onSaved={setPlayer} />}
          <p className="mt-2 max-w-xl text-muted">
            {fresh
              ? "Practice. Improve. Level up. Every answer is checked by code, not guessed by AI."
              : player.practiced_today
                ? "You've trained today. One more round keeps the weak spots shrinking."
                : "Pick up where you left off, or hit your weakest topic first."}
          </p>
        </div>
        <div className="flex gap-10">
          <CountStat value={player.stats.bosses_defeated} label="Bosses beaten" />
          <CountStat value={solved} of={problems.length} label="Problems solved" tone="cyan" />
          <CountStat value={player.best_streak} label="Best streak" tone="xp" />
        </div>
      </section>

      {/* Quest banner */}
      <section className="relative overflow-hidden rounded-panel border border-violet/40 shadow-[0_0_40px_-12px_rgba(139,92,246,0.6)]">
        <QuestBanner className="absolute inset-0 h-full w-full" />
        <div className="relative max-w-xl bg-gradient-to-r from-[#1E1250]/80 via-[#1E1250]/40 to-transparent px-6 py-8 md:px-8 md:py-10">
          <p className="h-display text-2xl italic text-white md:text-3xl">Your study quest awaits…</p>
          <p className="mt-2 text-[15px] text-white/85">Study any class, grind coding problems and run mock interviews, all in one game.</p>
        </div>
      </section>

      {/* The three modes */}
      <section aria-labelledby="modes" className="grid gap-5 lg:grid-cols-3">
        <h2 id="modes" className="sr-only">
          Training modes
        </h2>
        <Link
          href={featured?.active_session_id ? `/exam/${featured.active_session_id}` : "/exam"}
          className="mode-card group border-violet/50 bg-gradient-to-br from-violet/25 via-violet/[0.08] to-surface shadow-[0_0_30px_-14px_rgba(139,92,246,0.9)] hover:border-violet"
        >
          <div className="flex items-start gap-4">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-violet/25 text-violet-soft ring-1 ring-violet/50">
              <Swords size={28} aria-hidden />
            </span>
            <div className="min-w-0">
              <h3 className="h-display text-2xl">Study</h3>
              <p className="text-sm text-muted">Turn your notes into a boss.</p>
            </div>
            <span className="chip ml-auto shrink-0 border-violet/50 bg-violet/15 text-violet-soft">{beaten} beaten</span>
          </div>
          <span className="btn-primary mt-5 w-full">
            <Play size={16} aria-hidden /> {featured?.active_session_id ? "Resume the fight" : "Start a boss fight"}
          </span>
          <div className="mt-5 flex items-center gap-3 border-t border-violet/25 pt-4">
            {featured && <BossArt courseId={featured.id} name={featured.boss_name} className="h-14 w-14 shrink-0" />}
            <div className="min-w-0 flex-1">
              <div className="text-xs text-muted">Current boss</div>
              <div className="truncate font-semibold">{featured ? featured.boss_name : "None yet"}</div>
              {featured && (
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink ring-1 ring-line">
                    <div className="h-full rounded-full bg-gradient-to-r from-[#FF3D66] to-hp" style={{ width: `${featured.hp}%` }} />
                  </div>
                  <span className="text-xs tabular-nums text-muted">{featured.hp} HP</span>
                </div>
              )}
            </div>
          </div>
        </Link>

        <Link
          href="/arena"
          className="mode-card group border-cyan/50 bg-gradient-to-br from-cyan/25 via-cyan/[0.08] to-surface shadow-[0_0_30px_-14px_rgba(59,130,246,0.9)] hover:border-cyan"
        >
          <div className="flex items-start gap-4">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-cyan/25 text-cyan-deep ring-1 ring-cyan/50">
              <Code2 size={28} aria-hidden />
            </span>
            <div className="min-w-0">
              <h3 className="h-display text-2xl">Code</h3>
              <p className="text-sm text-muted">Solve. Prove. Level up.</p>
            </div>
            <span className="chip ml-auto shrink-0 border-cyan/50 bg-cyan/15 text-cyan-deep">
              {solved}/{problems.length}
            </span>
          </div>
          <span className="btn-cyan mt-5 w-full">Start a problem</span>
          <div className="mt-5 grid grid-cols-2 border-t border-cyan/25 pt-4">
            <div>
              <div className="text-xs text-muted">Day streak</div>
              <div className="mt-1 flex items-center gap-1.5 font-pixel text-2xl">
                <Flame size={20} className="text-xp" aria-hidden /> {player.streak} {player.streak === 1 ? "day" : "days"}
              </div>
            </div>
            <div className="border-l border-cyan/25 pl-4">
              <div className="text-xs text-muted">Problems solved</div>
              <div className="mt-1 flex items-center gap-1.5 font-pixel text-2xl">
                <Trophy size={20} className="text-xp" aria-hidden /> {solved}
              </div>
            </div>
          </div>
        </Link>

        <Link
          href="/interview"
          className="mode-card group border-heal/50 bg-gradient-to-br from-heal/25 via-heal/[0.08] to-surface shadow-[0_0_30px_-14px_rgba(34,197,94,0.9)] hover:border-heal"
        >
          <div className="flex items-start gap-4">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-heal/25 text-heal ring-1 ring-heal/50">
              <Mic size={28} aria-hidden />
            </span>
            <div className="min-w-0">
              <h3 className="h-display text-2xl">Interview</h3>
              <p className="text-sm text-muted">Get ready for what&apos;s next.</p>
            </div>
            <span className="chip ml-auto shrink-0 border-heal/50 bg-heal/15 text-heal">{doneInterviews} done</span>
          </div>
          <span className="btn mt-5 w-full bg-heal text-night shadow-[0_6px_20px_-8px_rgba(34,197,94,0.8)] hover:brightness-110">Start a mock interview</span>
          <div className="mt-5 grid grid-cols-2 border-t border-heal/25 pt-4">
            <div>
              <div className="text-xs text-muted">Finished</div>
              <div className="mt-1 font-pixel text-2xl">{doneInterviews}</div>
            </div>
            <div className="border-l border-heal/25 pl-4">
              <div className="text-xs text-muted">Last run</div>
              <div className="mt-1 font-semibold">{lastInterview ? timeAgo(lastInterview.started_at) : "Not yet"}</div>
            </div>
          </div>
        </Link>
      </section>

      {/* Progress and recent activity */}
      <section className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <div className="panel grid gap-6 p-6 md:grid-cols-[1fr_auto_220px]">
          <div>
            <h2 className="h-display text-xl">Your progress</h2>
            <div className="mt-5 grid grid-cols-3 gap-4">
              <Ring value={studyMastery} label="Study" sub="avg mastery" color="#8B5CF6" />
              <Ring value={problems.length ? solved / problems.length : null} label="Coding" sub="problems solved" color="#3B82F6" />
              <Ring value={courses.length ? beaten / courses.length : null} label="Bosses" sub="beaten at least once" color="#22C55E" />
            </div>
          </div>
          <div className="hidden w-px bg-line md:block" />
          <div className="flex flex-col justify-center">
            <div className="h-display text-3xl">Level {player.level}</div>
            <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-ink ring-1 ring-line">
              <div
                className="h-full rounded-full bg-gradient-to-r from-violet to-[#C084FC] shadow-[0_0_12px_rgba(139,92,246,0.8)]"
                style={{ width: `${(player.xp_into_level / Math.max(1, player.xp_for_next)) * 100}%` }}
              />
            </div>
            <div className="mt-1.5 text-sm tabular-nums text-muted">
              {player.xp_into_level} / {player.xp_for_next} XP
            </div>
            <Link href="/settings" className="mt-4 flex items-center gap-2 rounded-chip border border-line bg-raised px-3 py-2 text-sm transition hover:border-xp/60">
              <Star size={16} className="fill-xp text-xp" aria-hidden />
              {player.achievements.unlocked} of {player.achievements.total} achievements
            </Link>
          </div>
        </div>
        <div className="panel p-6">
          <h2 className="h-display flex items-center gap-2 text-xl">
            <Zap size={18} className="fill-xp text-xp" aria-hidden /> Recent activity
          </h2>
          {player.recent_xp.length === 0 ? (
            <p className="mt-3 text-sm text-muted">{player.xp_rules}</p>
          ) : (
            <ul className="mt-3 divide-y divide-line text-sm">
              {player.recent_xp.slice(0, 5).map((x, i) => (
                <li key={i} className="flex items-center gap-3 py-2.5">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-raised">{xpIcon(x.reason)}</span>
                  <span className="min-w-0 flex-1 truncate">{XP_REASON[x.reason] ?? x.reason}</span>
                  <span className="text-right">
                    <span className="block font-display font-semibold tabular-nums text-violet-soft">+{x.amount} XP</span>
                    <span className="block text-xs text-muted">{timeAgo(x.created_at)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        <div className="panel p-6">
          <h2 className="h-display text-xl">Weak spots</h2>
          <p className="mt-1 text-sm text-muted">Lowest mastery first, from your actual answers. Mastery fades when you stop practicing a topic. Pale bars have fewer than 3 answers behind them.</p>
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
                    {t.fading >= 0.005 && <span className="chip ml-2 border-hp/40 text-hp">fading −{Math.round(t.fading * 100)}%</span>}
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
          <RaidCard raid={player.raid} />
          <Link href="/party" className="panel lift group flex items-center gap-4 p-5 hover:border-cyan/60">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-cyan/15 text-cyan ring-1 ring-cyan/40">
              <Users size={22} aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="h-display block text-lg">Party raid</span>
              <span className="block text-sm text-muted">One boss, shared HP, up to 8 friends on your Wi-Fi.</span>
            </span>
          </Link>
          <div className="panel p-6">
            <h2 className="h-display text-xl">Continue</h2>
            <ul className="mt-4 space-y-2 text-sm">
              {player.continue.exam && (
                <li>
                  <Link className="flex justify-between rounded-chip bg-raised px-3 py-2.5 transition hover:bg-violet/10 hover:text-violet-deep" href={`/exam/${player.continue.exam.id}`}>
                    <span>Fight {player.continue.exam.boss_name}</span>
                    <span className="text-hp">{player.continue.exam.hp_current} HP</span>
                  </Link>
                </li>
              )}
              {player.continue.coding && (
                <li>
                  <Link className="flex justify-between rounded-chip bg-raised px-3 py-2.5 transition hover:bg-violet/10 hover:text-violet-deep" href={`/arena/${player.continue.coding.slug}`}>
                    <span>{problems.find((p) => p.slug === player.continue.coding?.slug)?.title ?? "Unsolved problem"}</span>
                    <span className="text-muted">{timeAgo(player.continue.coding.last)}</span>
                  </Link>
                </li>
              )}
              {player.continue.interview && (
                <li>
                  <Link className="flex justify-between rounded-chip bg-raised px-3 py-2.5 transition hover:bg-violet/10 hover:text-violet-deep" href={`/interview/${player.continue.interview.id}`}>
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
        </div>
      </section>
    </div>
  );
}
