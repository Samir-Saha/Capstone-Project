"use client";

import { Check, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { BossArt } from "@/components/BossArt";
import { SegmentedHp } from "@/components/Hud";
import { TeX } from "@/components/Math";
import { StepsView } from "@/components/Steps";
import { ErrorNote, Spinner, Stat } from "@/components/ui";
import { api, type FightResults } from "@/lib/api";

const TITLE: Record<string, string> = {
  victory: "Boss defeated",
  knocked_out: "Knocked out",
  out_of_questions: "Round over",
  retreated: "Retreated",
};

export default function Results() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<FightResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.results(id));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <ErrorNote message={error} onRetry={load} />;
  if (!data) return <Spinner label="Tallying the fight" />;
  const s = data.session;
  if (s.status === "active")
    return (
      <div className="panel p-8">
        <p>This fight is still going.</p>
        <Link className="btn-primary mt-4" href={`/exam/${id}`}>
          Back to the fight
        </Link>
      </div>
    );

  const again = async () => {
    setStarting(true);
    try {
      const f = await api.startFight(s.course_id);
      router.push(`/exam/${f.id}`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="space-y-8">
      <section className="panel grid items-center gap-6 p-6 md:grid-cols-[140px_1fr_auto]">
        <BossArt courseId={s.course_id} name={s.boss_name} state={s.outcome === "victory" ? "defeated" : "idle"} className="mx-auto h-32 w-32" />
        <div>
          <p className="text-sm text-muted">{s.course_name}</p>
          <h1 className={`h-display text-4xl ${s.outcome === "victory" ? "text-heal" : ""}`}>
            {s.kind === "raid"
              ? s.outcome === "victory"
                ? "Raid cleared"
                : "Raid over"
              : `${TITLE[s.outcome ?? ""] ?? "Fight over"}: ${s.boss_name}`}
          </h1>
          <div className="mt-4 max-w-xl">
            <SegmentedHp topics={s.topics} hp={s.hp} victoryHp={s.victory_hp} compact />
            <p className="mt-2 text-sm text-muted">
              Started at {s.hp_start} HP, ended at {s.hp} HP.
            </p>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <button type="button" className="btn-primary" onClick={again} disabled={starting}>
            {starting ? "Opening" : "Fight again"}
          </button>
          <Link className="btn-ghost" href="/exam">
            All bosses
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-6 md:grid-cols-4">
        <Stat value={`${s.correct}/${s.answered}`} label="Correct answers" tone="heal" />
        <Stat value={s.best_combo} label="Best streak" tone="xp" />
        <Stat value={`+${data.xp_earned}`} label="XP earned" tone="xp" />
        <div>
          <div className="flex items-center gap-2 font-display text-3xl font-bold text-heal">
            <ShieldCheck size={26} aria-hidden /> {data.grading.verified}
          </div>
          <div className="text-sm text-muted">Graded by math, {data.grading.ai_evaluated} by AI</div>
        </div>
      </section>

      <section className="panel p-6">
        <h2 className="h-display text-xl">Mastery by topic</h2>
        <p className="mt-1 text-sm text-muted">Bayesian Knowledge Tracing estimate from your answers. The faint bar is where you started this fight.</p>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead className="text-left text-muted">
              <tr>
                <th className="pb-2 font-medium">Topic</th>
                <th className="pb-2 font-medium">This fight</th>
                <th className="w-1/2 pb-2 font-medium">Mastery</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.topics.map((t) => (
                <tr key={t.id}>
                  <td className="py-3 pr-4">{t.name}</td>
                  <td className="py-3 pr-4 tabular-nums text-muted">{t.asked ? `${t.right}/${t.asked}` : "Not asked"}</td>
                  <td className="py-3">
                    <div className="flex items-center gap-3">
                      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-ink ring-1 ring-line">
                        <div className="absolute inset-y-0 left-0 bg-violet/30" style={{ width: `${t.mastery_start * 100}%` }} />
                        <div
                          className={`absolute inset-y-0 left-0 ${t.mastery >= t.mastery_start ? "bg-violet" : "bg-hp"}`}
                          style={{ width: `${t.mastery * 100}%` }}
                        />
                      </div>
                      <span className="w-24 text-right tabular-nums">
                        {Math.round(t.mastery_start * 100)}% <span className="text-muted">to</span> {Math.round(t.mastery * 100)}%
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.next_steps.length > 0 && (
          <div className="mt-6 border-t border-line pt-4 text-sm">
            <span className="font-semibold">Next: </span>
            {data.next_steps.join(". ")}.
          </div>
        )}
      </section>

      <section className="panel p-6">
        <h2 className="h-display text-xl">Every attack</h2>
        <ol className="mt-4 divide-y divide-line">
          {data.attempts.map((a, i) => (
            <li key={i} className="grid gap-3 py-4 md:grid-cols-[28px_1fr_1fr]">
              <span className={`mt-1 flex h-6 w-6 items-center justify-center rounded-full ${a.correct ? "bg-heal/20 text-heal" : "bg-hp/20 text-hp"}`}>
                {a.correct ? <Check size={14} aria-label="Correct" /> : <X size={14} aria-label="Incorrect" />}
              </span>
              <div className="min-w-0">
                <p className="text-xs text-muted">{a.topic}</p>
                <p className="text-sm">{a.prompt}</p>
                {a.latex && (
                  <div className="mt-1 overflow-x-auto">
                    <TeX tex={a.latex} />
                  </div>
                )}
              </div>
              <div className="min-w-0 text-sm">
                <p>
                  <span className="text-muted">You: </span>
                  <span className="font-mono">{a.answer}</span>
                  {a.hint_used && <span className="chip ml-2">hint</span>}
                  {a.rematch && <span className="chip ml-2 border-violet/50 text-violet-soft">rematch</span>}
                </p>
                <p className="mt-1">
                  <span className="text-muted">Answer: </span>
                  {a.answer_latex ? <TeX tex={a.answer_latex} /> : "—"}
                </p>
                {!a.correct && a.method && <p className="mt-1 text-muted">{a.method}</p>}
                {a.steps && a.steps.lines.length > 0 && (
                  <div className="mt-2">
                    <StepsView report={a.steps} compact />
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
        {data.attempts.length === 0 && <p className="mt-3 text-muted">No answers in this fight.</p>}
      </section>
    </div>
  );
}
