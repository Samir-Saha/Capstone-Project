"use client";

import { ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AchievementIcon } from "@/components/AchievementIcon";
import { DailyBars, MasteryChart } from "@/components/Charts";
import { ErrorNote, Spinner, Stat } from "@/components/ui";
import { api, type ProgressData } from "@/lib/api";

const SUBJECT: Record<string, string> = {
  math_template: "Boss questions",
  coding_problem: "Arena problems",
  generated_template: "Questions from your PDFs",
};

export default function ProgressPage() {
  const [data, setData] = useState<ProgressData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [course, setCourse] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.progress();
      setData(d);
      setCourse((c) => c ?? d.mastery_history[0]?.course_id ?? null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <ErrorNote message={error} onRetry={load} />;
  if (!data) return <Spinner label="Adding up your training" />;
  const t = data.totals;
  const hist = data.mastery_history.find((h) => h.course_id === course) ?? data.mastery_history[0];
  const unlocked = data.achievements.filter((a) => a.unlocked_at).length;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="h-display text-4xl">Progress</h1>
        <p className="mt-2 max-w-2xl text-muted">Everything here comes from recorded answers, submissions and interviews on this computer.</p>
      </header>

      <section className="panel grid grid-cols-2 gap-6 p-6 md:grid-cols-5">
        <Stat value={t.answered} label="Questions answered" />
        <Stat value={t.accuracy === null ? "–" : `${Math.round(t.accuracy * 100)}%`} label="Correct" tone="heal" />
        <Stat value={t.problems_solved} label="Problems solved" tone="cyan" />
        <Stat value={t.clean_work} label="Fully correct worked answers" tone="xp" />
        <Stat value={t.interviews} label="Interviews finished" />
      </section>

      {data.readiness && data.readiness.length > 0 && (
        <section className="panel p-6" aria-labelledby="ready-title">
          <h2 id="ready-title" className="h-display text-xl">
            Exam readiness
          </h2>
          <p className="mt-1 text-sm text-muted">
            Average mastery after forgetting is applied. A topic counts as ready at 75%, the same bar a boss fight uses.
          </p>
          <ul className="mt-5 grid gap-5 md:grid-cols-2">
            {data.readiness.map((r) => {
              const pct = Math.round(r.readiness * 100);
              const tone = r.readiness >= 0.75 ? "bg-heal" : r.readiness >= 0.5 ? "bg-xp" : "bg-hp";
              const todo = r.weakest.filter((w) => w.mastery < 0.75);
              return (
                <li key={r.course_id} className="rounded-xl p-4 ring-1 ring-line">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-semibold">{r.course}</span>
                    <span className="h-display text-2xl tabular-nums">{pct}%</span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-ink ring-1 ring-line">
                    <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
                  </div>
                  <p className="mt-2 text-sm text-muted">
                    {r.ready_topics}/{r.total_topics} topics ready
                    {r.fading_topics > 0 && `, ${r.fading_topics} fading since last practice`}
                  </p>
                  {todo.length > 0 ? (
                    <div className="mt-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted">Practice next</p>
                      <ul className="mt-1.5 space-y-1 text-sm">
                        {todo.map((w) => (
                          <li key={w.name} className="flex justify-between gap-3">
                            <span>{w.name}</span>
                            <span className="tabular-nums text-muted">
                              {Math.round(w.mastery * 100)}%
                              {w.attempts > 0 ? ` · ${w.attempts} answered` : " · not tried"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-heal">Every topic is at the bar. Keep it there with a short daily fight.</p>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section className="panel p-6" aria-labelledby="mastery-title">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 id="mastery-title" className="h-display text-xl">
            Mastery over time
          </h2>
          {data.mastery_history.length > 1 && (
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Course">
              {data.mastery_history.map((h) => (
                <button
                  key={h.course_id}
                  type="button"
                  role="tab"
                  aria-selected={h.course_id === hist?.course_id}
                  onClick={() => setCourse(h.course_id)}
                  className={`rounded-full border px-3 py-1 text-sm ${h.course_id === hist?.course_id ? "border-violet bg-violet/15" : "border-line text-muted hover:text-text"}`}
                >
                  {h.course}
                </button>
              ))}
            </div>
          )}
        </div>
        <p className="mt-1 text-sm text-muted">Bayesian Knowledge Tracing estimate per topic, updated after every graded answer.</p>
        <div className="mt-5">
          {hist ? <MasteryChart topics={hist.topics} events={hist.events} /> : <p className="text-muted">Fight a boss to start tracking mastery.</p>}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <section className="panel min-w-0 p-6" aria-labelledby="xp-title">
          <h2 id="xp-title" className="h-display text-xl">
            XP, last 14 days
          </h2>
          <div className="mt-4">
            <DailyBars data={data.xp_by_day} />
          </div>
        </section>
        <section className="panel min-w-0 p-6" aria-labelledby="acc-title">
          <h2 id="acc-title" className="h-display text-xl">
            Accuracy by course
          </h2>
          {data.accuracy_by_course.length === 0 ? (
            <p className="mt-3 text-muted">No answers yet.</p>
          ) : (
            <ul className="mt-4 space-y-4">
              {data.accuracy_by_course.map((c) => {
                const pct = c.answered ? c.correct / c.answered : 0;
                return (
                  <li key={c.course}>
                    <div className="flex justify-between text-sm">
                      <span>{c.course}</span>
                      <span className="tabular-nums text-muted">
                        {c.correct}/{c.answered}, {Math.round(pct * 100)}%
                      </span>
                    </div>
                    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-ink ring-1 ring-line">
                      <div className="h-full rounded-full bg-heal" style={{ width: `${pct * 100}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      <section className="panel p-6" aria-labelledby="verify-title">
        <h2 id="verify-title" className="h-display flex items-center gap-2 text-xl">
          <ShieldCheck size={20} className="text-heal" aria-hidden /> Verification record
        </h2>
        <p className="mt-1 text-sm text-muted">
          Every question and problem is checked before it reaches you. This is the running count, including what got thrown out.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[480px] text-sm">
            <thead className="text-left text-muted">
              <tr>
                <th className="pb-2 font-medium">Content</th>
                <th className="pb-2 text-right font-medium">Verified</th>
                <th className="pb-2 text-right font-medium">Rejected</th>
                <th className="pb-2 text-right font-medium">Unsupported</th>
                <th className="pb-2 text-right font-medium">Rejection rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {Object.entries(data.verification).map(([subject, counts]) => {
                const v = counts.verified ?? 0;
                const r = counts.rejected ?? 0;
                const u = counts.unsupported ?? 0;
                const total = v + r + u;
                return (
                  <tr key={subject}>
                    <td className="py-2.5">{SUBJECT[subject] ?? subject}</td>
                    <td className="py-2.5 text-right tabular-nums">{v}</td>
                    <td className="py-2.5 text-right tabular-nums">{r}</td>
                    <td className="py-2.5 text-right tabular-nums">{u}</td>
                    <td className="py-2.5 text-right tabular-nums">{total ? `${(((r + u) / total) * 100).toFixed(1)}%` : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {data.rejection_reasons.length > 0 && (
          <div className="mt-4 text-sm">
            <div className="text-muted">Most common reasons for rejection</div>
            <ul className="mt-1 list-disc pl-5">
              {data.rejection_reasons.map((r, i) => (
                <li key={i}>
                  {r.reason} <span className="text-muted">({r.n})</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="panel p-6" aria-labelledby="ach-title">
        <h2 id="ach-title" className="h-display text-xl">
          Achievements{" "}
          <span className="text-base font-normal text-muted">
            {unlocked} of {data.achievements.length}
          </span>
        </h2>
        <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.achievements.map((a) => (
            <li
              key={a.key}
              className={`flex items-start gap-3 rounded-chip border p-3 ${a.unlocked_at ? "border-xp/40 bg-xp/5" : "border-line opacity-55"}`}
            >
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${a.unlocked_at ? "bg-xp/20 text-xp" : "bg-raised text-muted"}`}>
                <AchievementIcon name={a.icon} size={18} />
              </span>
              <div className="min-w-0">
                <div className="font-display font-semibold">{a.name}</div>
                <div className="text-sm text-muted">{a.text}</div>
                {a.unlocked_at && <div className="mt-0.5 text-xs text-xp">Unlocked {new Date(a.unlocked_at).toLocaleDateString()}</div>}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
