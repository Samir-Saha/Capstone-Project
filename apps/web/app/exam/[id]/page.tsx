"use client";

import { Flag, Lightbulb, ShieldCheck, Zap } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { BossArt } from "@/components/BossArt";
import { DifficultyPips, Hearts, SegmentedHp } from "@/components/Hud";
import { TeX } from "@/components/Math";
import { ErrorNote, Spinner } from "@/components/ui";
import { api, notifyProgress, type AnswerFeedback, type Fight } from "@/lib/api";
import { play } from "@/lib/sound";

type Graded = Extract<AnswerFeedback, { status: "graded" }>;
type Floater = { id: number; text: string; tone: "dmg" | "heal" };

const OUTCOME: Record<string, { title: string; body: string; tone: string }> = {
  victory: { title: "Boss defeated", body: "Average mastery is at 75% or better across every topic.", tone: "text-heal" },
  knocked_out: { title: "Knocked out", body: "Out of hearts. Your progress still counts: mastery only moves with real answers.", tone: "text-hp" },
  out_of_questions: { title: "Round over", body: "That was all 15 questions. The boss keeps the HP you took off it.", tone: "text-xp" },
  retreated: { title: "You retreated", body: "Answers you gave still count toward mastery.", tone: "text-muted" },
};

export default function FightPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [fight, setFight] = useState<Fight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [summoning, setSummoning] = useState(false);
  const [answer, setAnswer] = useState("");
  const [preview, setPreview] = useState<{ latex: string | null; error: string | null }>({ latex: null, error: null });
  const [grading, setGrading] = useState(false);
  const [feedback, setFeedback] = useState<Graded | null>(null);
  const [parseNote, setParseNote] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [bossState, setBossState] = useState<"idle" | "hit" | "attack" | "defeated">("idle");
  const [shake, setShake] = useState(false);
  const [floaters, setFloaters] = useState<Floater[]>([]);
  const [confirmRetreat, setConfirmRetreat] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);

  const summon = useCallback(async () => {
    setSummoning(true);
    setError(null);
    try {
      const f = await api.nextQuestion(id);
      setFight(f);
      setHint(f.current_question?.hint ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSummoning(false);
    }
  }, [id]);

  const load = useCallback(async () => {
    try {
      const f = await api.fight(id);
      setFight(f);
      if (f.status !== "active") {
        setBossState(f.outcome === "victory" ? "defeated" : "idle");
        return;
      }
      if (f.current_question) setHint(f.current_question.hint);
      else await summon();
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id, summon]);

  useEffect(() => {
    void load();
  }, [load]);

  const q = fight?.current_question ?? null;

  // Live preview of how the answer was read.
  useEffect(() => {
    if (!answer.trim()) {
      setPreview({ latex: null, error: null });
      return;
    }
    const t = setTimeout(async () => {
      try {
        setPreview(await api.preview(answer));
      } catch {
        /* preview is optional */
      }
    }, 250);
    return () => clearTimeout(t);
  }, [answer]);

  useEffect(() => {
    if (q && !feedback && !grading) inputRef.current?.focus();
  }, [q, feedback, grading]);
  useEffect(() => {
    if (feedback) nextRef.current?.focus();
  }, [feedback]);

  const float = (text: string, tone: Floater["tone"]) => {
    const f = { id: Date.now() + Math.random(), text, tone };
    setFloaters((xs) => [...xs, f]);
    setTimeout(() => setFloaters((xs) => xs.filter((x) => x.id !== f.id)), 1300);
  };

  const strike = async () => {
    if (!q || !answer.trim() || grading) return;
    setGrading(true);
    setParseNote(null);
    try {
      const fb = await api.answer(id, q.id, answer);
      if (fb.status === "unparseable") {
        setParseNote(fb.message);
        return;
      }
      setFeedback(fb);
      if (fb.correct) {
        setBossState("hit");
        play("hit");
        if (fb.damage > 0) float(`−${fb.damage}`, "dmg");
      } else {
        setBossState("attack");
        setShake(true);
        play("miss");
        if (fb.damage < 0) float(`+${-fb.damage} HP`, "heal");
        setTimeout(() => setShake(false), 350);
      }
      setTimeout(() => setBossState(fb.session.outcome === "victory" ? "defeated" : "idle"), 520);
      if (fb.session.status !== "active") setTimeout(() => play(fb.session.outcome === "victory" ? "victory" : "defeat"), 600);
      notifyProgress(fb.xp);
      // Keep the old question on screen with feedback; update HUD numbers.
      setFight({ ...fb.session, current_question: q });
    } catch (e) {
      setParseNote((e as Error).message);
    } finally {
      setGrading(false);
    }
  };

  const next = async () => {
    if (!feedback) return;
    if (feedback.session.status !== "active") {
      router.push(`/exam/${id}/results`);
      return;
    }
    setFeedback(null);
    setAnswer("");
    setHint(null);
    setPreview({ latex: null, error: null });
    await summon();
  };

  const useHint = async () => {
    if (!q) return;
    try {
      setHint((await api.hint(id, q.id)).hint);
    } catch (e) {
      setParseNote((e as Error).message);
    }
  };

  const retreat = async () => {
    await api.retreat(id);
    router.push(`/exam/${id}/results`);
  };

  if (error && !fight) return <ErrorNote message={error} onRetry={load} />;
  if (!fight) return <Spinner label="Entering the arena" />;

  const over = fight.status !== "active";
  const outcome = fight.outcome ? OUTCOME[fight.outcome] : null;

  return (
    <div className={`grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] ${shake ? "animate-shake" : ""}`}>
      {/* Boss column */}
      <section className="panel relative flex flex-col overflow-hidden p-6" aria-label="Boss">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-56 bg-[radial-gradient(ellipse_at_50%_0%,rgba(139,108,255,0.22),transparent_70%)]" />
        <div className="relative flex items-start justify-between gap-3">
          <div>
            <p className="text-sm text-muted">
              {fight.course_name}
              {fight.course_code ? ` (${fight.course_code})` : ""}
            </p>
            <h1 className="h-display text-2xl">{fight.boss_name}</h1>
          </div>
          {!over &&
            (confirmRetreat ? (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted">Leave the fight?</span>
                <button type="button" className="btn-ghost px-3 py-1 text-sm" onClick={retreat}>
                  Retreat
                </button>
                <button type="button" className="px-2 py-1 text-sm text-muted hover:text-text" onClick={() => setConfirmRetreat(false)}>
                  Stay
                </button>
              </div>
            ) : (
              <button type="button" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-text" onClick={() => setConfirmRetreat(true)}>
                <Flag size={15} aria-hidden /> Retreat
              </button>
            ))}
        </div>
        <div className="relative mt-5">
          <SegmentedHp topics={fight.topics} hp={fight.hp} victoryHp={fight.victory_hp} activeTopicId={over ? null : q?.topic_id} />
        </div>
        <div className="relative mx-auto my-4 flex h-[260px] w-[260px] items-center justify-center xl:h-[300px] xl:w-[300px]">
          <BossArt courseId={fight.course_id} name={fight.boss_name} state={over && fight.outcome === "victory" ? "defeated" : bossState} className="h-full w-full" />
          {floaters.map((f) => (
            <span
              key={f.id}
              className={`pointer-events-none absolute left-1/2 top-1/3 -translate-x-1/2 animate-rise font-display text-5xl font-bold drop-shadow-[0_4px_12px_rgba(0,0,0,0.8)] ${
                f.tone === "dmg" ? "text-xp" : "text-hp"
              }`}
              aria-hidden
            >
              {f.text}
            </span>
          ))}
        </div>
        <div className="relative mt-auto flex flex-wrap items-center justify-between gap-4 border-t border-line pt-4">
          <Hearts hearts={fight.hearts} max={fight.max_hearts} />
          <div className="flex items-center gap-5 font-display text-sm">
            <span className={`inline-flex items-center gap-1 ${fight.combo >= 3 ? "text-xp" : "text-muted"}`} title="Correct answers in a row. Every 3 adds bonus XP.">
              <Zap size={15} className={fight.combo >= 3 ? "fill-xp" : ""} aria-hidden />
              {fight.combo} streak
            </span>
            <span className="tabular-nums text-muted">
              {Math.min(fight.answered + (feedback ? 0 : q ? 1 : 0), fight.question_target)} / {fight.question_target}
            </span>
          </div>
        </div>
      </section>

      {/* Question column */}
      <section className="panel flex flex-col p-6 md:p-8 lg:min-h-[520px]" aria-label="Question" aria-live="polite">
        {over && outcome ? (
          <div className="m-auto max-w-md animate-pop text-center">
            <p className={`h-display text-5xl ${outcome.tone}`}>{outcome.title}</p>
            <p className="mt-3 text-muted">{outcome.body}</p>
            <p className="mt-6 font-display text-lg">
              {fight.correct} of {fight.answered} correct, best streak {fight.best_combo}
            </p>
            <div className="mt-8 flex justify-center gap-3">
              <Link href={`/exam/${id}/results`} className="btn-primary">
                See the breakdown
              </Link>
              <Link href="/exam" className="btn-ghost">
                Back to bosses
              </Link>
            </div>
          </div>
        ) : summoning || !q ? (
          <div className="m-auto text-center">
            <Spinner label="The boss is preparing an attack. Verifying the answer key" />
            {error && (
              <div className="mt-4">
                <ErrorNote message={error} onRetry={summon} />
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="chip border-xp/50 text-xp">{q.topic}</span>
              <DifficultyPips level={q.difficulty} />
              <span
                className="ml-auto inline-flex items-center gap-1.5 text-heal"
                title={`Answer key checked by: ${q.verification.checks.join(", ")}`}
              >
                <ShieldCheck size={15} aria-hidden /> Key verified
              </span>
            </div>

            <p className="mt-6 text-lg leading-relaxed">{q.prompt}</p>
            {q.latex && (
              <div className="math-hero mt-5 overflow-x-auto rounded-panel border border-line bg-ink/60 px-6 py-8 text-center">
                <TeX tex={q.latex} display />
              </div>
            )}

            {!feedback ? (
              <form
                className="mt-auto pt-8"
                onSubmit={(e) => {
                  e.preventDefault();
                  void strike();
                }}
              >
                <label htmlFor="answer" className="label">
                  Your answer <span className="font-normal">({q.answer_format})</span>
                </label>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <input
                    id="answer"
                    ref={inputRef}
                    className="field font-mono text-lg"
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                    disabled={grading}
                    aria-describedby="answer-preview"
                  />
                  <button type="submit" className="btn-primary shrink-0 px-6" disabled={!answer.trim() || grading}>
                    {grading ? "Checking" : "Strike"}
                    <span className="kbd">Enter</span>
                  </button>
                </div>
                <div id="answer-preview" className="mt-2 min-h-[28px] text-sm">
                  {preview.latex ? (
                    <span className="text-muted">
                      Reads as <TeX tex={preview.latex} />
                    </span>
                  ) : preview.error ? (
                    <span className="text-muted">Not readable yet: {preview.error}</span>
                  ) : null}
                </div>
                {parseNote && (
                  <p className="mt-1 text-sm text-xp" role="alert">
                    {parseNote}
                  </p>
                )}
                <div className="mt-4 flex items-start gap-3 border-t border-line pt-4 text-sm">
                  {hint ? (
                    <p className="flex items-start gap-2 text-text">
                      <Lightbulb size={16} className="mt-0.5 shrink-0 text-xp" aria-hidden /> {hint}
                    </p>
                  ) : (
                    <button type="button" className="inline-flex items-center gap-1.5 text-muted hover:text-text" onClick={useHint}>
                      <Lightbulb size={16} aria-hidden /> Show a hint (halves the XP for this one)
                    </button>
                  )}
                </div>
              </form>
            ) : (
              <div className="mt-auto animate-pop pt-8">
                <div
                  className={`rounded-panel border p-5 ${feedback.correct ? "border-heal/50 bg-heal/10" : "border-hp/50 bg-hp/10"}`}
                  role="status"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className={`h-display text-3xl ${feedback.correct ? "text-heal" : "text-hp"}`}>{feedback.correct ? "Direct hit" : "Blocked"}</p>
                    <p className="text-sm text-muted">
                      {feedback.correct ? `−${feedback.damage} boss HP` : `You lost a heart`}
                      {feedback.xp > 0 && <span className="ml-3 font-display font-semibold text-xp">+{feedback.xp} XP</span>}
                    </p>
                  </div>
                  <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[auto_1fr]">
                    <dt className="text-muted">You answered</dt>
                    <dd className="font-mono">{feedback.your_answer}</dd>
                    <dt className="text-muted">Answer</dt>
                    <dd>{feedback.answer_latex ? <TeX tex={feedback.answer_latex} /> : <span className="font-mono">{feedback.answer}</span>}</dd>
                    {feedback.method && (
                      <>
                        <dt className="text-muted">How</dt>
                        <dd>{feedback.method}</dd>
                      </>
                    )}
                    <dt className="text-muted">{q.topic}</dt>
                    <dd>
                      Mastery{" "}
                      <span className="tabular-nums">{Math.round(feedback.mastery_before * 100)}%</span> to{" "}
                      <span className={`font-semibold tabular-nums ${feedback.mastery_after >= feedback.mastery_before ? "text-heal" : "text-hp"}`}>
                        {Math.round(feedback.mastery_after * 100)}%
                      </span>
                    </dd>
                  </dl>
                  <p className="mt-4 text-xs text-muted">Graded by {feedback.grading.method}, not by AI.</p>
                </div>
                <button ref={nextRef} type="button" className="btn-primary mt-5 w-full py-3" onClick={next}>
                  {feedback.session.status === "active" ? "Next attack" : "See how the fight went"}
                  <span className="kbd">Enter</span>
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
