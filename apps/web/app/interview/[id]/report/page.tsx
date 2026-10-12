"use client";

import { Bot, Check, Ruler, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, Spinner, Stat } from "@/components/ui";
import { api, type InterviewReport, type Turn } from "@/lib/api";

const SOURCE_LABEL: Record<string, string> = { behavioral: "Behavioral", resume: "Resume", follow_up: "Follow-up", technical: "Coding" };

function Tick({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? <Check size={16} className="mt-0.5 shrink-0 text-heal" aria-label="Yes" /> : <X size={16} className="mt-0.5 shrink-0 text-hp" aria-label="No" />}
      <span>{children}</span>
    </li>
  );
}

function StarBars({ fb }: { fb: NonNullable<Turn["ai_feedback"]> }) {
  const rows: [string, number][] = [
    ["Situation", fb.situation],
    ["Task", fb.task],
    ["Action", fb.action],
    ["Result", fb.result],
    ["Specificity", fb.specificity],
  ];
  return (
    <div className="grid gap-1.5">
      {rows.map(([label, v]) => (
        <div key={label} className="grid grid-cols-[90px_1fr_28px] items-center gap-2 text-sm">
          <span className="text-muted">{label}</span>
          <div className="flex gap-1">
            {[1, 2, 3, 4].map((i) => (
              <span key={i} className={`h-2 flex-1 rounded-sm ${i <= v ? "bg-violet" : "bg-line"}`} />
            ))}
          </div>
          <span className="text-right tabular-nums">{v}/4</span>
        </div>
      ))}
    </div>
  );
}

function TurnCard({ t, aiAvailable }: { t: Turn; aiAvailable: boolean }) {
  const m = t.metrics;
  const fillers = Object.entries(m.fillers);
  return (
    <li className="panel p-6">
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip">{SOURCE_LABEL[t.source] ?? t.source}</span>
        <span className="chip">{t.input_mode === "voice" ? "Spoken" : "Typed"}</span>
      </div>
      <p className="mt-3 font-display text-lg leading-snug">{t.question}</p>
      <blockquote className="mt-3 border-l-2 border-line pl-4 text-[15px] leading-relaxed text-muted">{t.answer || "(no explanation)"}</blockquote>

      <div className="mt-5 grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="flex items-center gap-1.5 font-display text-sm font-semibold text-cyan">
            <Ruler size={15} aria-hidden /> Measured
          </h3>
          {t.input_mode === "voice" && m.speaking_s !== undefined ? (
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted">Speaking time</dt>
              <dd className="tabular-nums">{m.speaking_s}s</dd>
              <dt className="text-muted">Pace</dt>
              <dd className="tabular-nums">{m.wpm ? `${m.wpm} wpm` : "Too short to measure"}</dd>
              <dt className="text-muted">Pauses over 0.6s</dt>
              <dd className="tabular-nums">
                {m.pause_count} ({m.long_pauses} over 2s)
              </dd>
              <dt className="text-muted">Filler words</dt>
              <dd className="tabular-nums">
                {m.filler_total}
                {m.fillers_per_min !== null && m.fillers_per_min !== undefined ? ` (${m.fillers_per_min}/min)` : ""}
              </dd>
            </dl>
          ) : (
            <p className="mt-2 text-sm text-muted">Typed answer, so pace and pauses weren't measured. {m.filler_total} filler words.</p>
          )}
          {fillers.length > 0 && <p className="mt-2 text-xs text-muted">{fillers.map(([w, n]) => `“${w}” ×${n}`).join(", ")}</p>}
          <ul className="mt-3 space-y-1.5 text-sm">
            <Tick ok={t.checks.length.ok}>{t.checks.length.words} words</Tick>
            <Tick ok={t.checks.mentions_number}>Mentions a number</Tick>
            <Tick ok={t.checks.result_language}>Says what the result was</Tick>
            <Tick ok={t.checks.ownership.ok}>
              Ownership: “I” {t.checks.ownership.i} times, “we” {t.checks.ownership.we}
            </Tick>
            {t.checks.explains_measurement !== undefined && <Tick ok={t.checks.explains_measurement}>Explains how it was measured</Tick>}
            {t.checks.code && (
              <Tick ok={t.checks.code.verdict === "accepted"}>
                Code: {t.checks.code.verdict.replace(/_/g, " ")}
                {t.checks.code.total ? ` (${t.checks.code.passed}/${t.checks.code.total} tests)` : ""}
              </Tick>
            )}
          </ul>
        </div>
        <div>
          <h3 className="flex items-center gap-1.5 font-display text-sm font-semibold text-violet-soft">
            <Bot size={15} aria-hidden /> AI evaluation
          </h3>
          {t.ai_feedback ? (
            <div className="mt-2 space-y-3 text-sm">
              <StarBars fb={t.ai_feedback} />
              {t.ai_feedback.quote && <p className="italic text-muted">“{t.ai_feedback.quote}”</p>}
              {t.ai_feedback.missing.length > 0 && <p>Missing: {t.ai_feedback.missing.join("; ")}</p>}
              <p>{t.ai_feedback.improvement}</p>
              <p className="text-xs text-muted">AI judgment, not a measurement.</p>
            </div>
          ) : (
            <p className="mt-2 text-sm text-muted">
              {t.source === "technical"
                ? "Coding answers are graded by tests instead."
                : aiAvailable
                  ? "No AI score for this answer."
                  : "Add an AI key (LLM_API_KEY and LLM_MODEL in .env) to get STAR scores. Everything on the left is measured without AI."}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

export default function Report() {
  const { id } = useParams<{ id: string }>();
  const [rep, setRep] = useState<InterviewReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setRep(await api.interviewReport(id));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <ErrorNote message={error} onRetry={load} />;
  if (!rep) return <Spinner label="Building your report" />;
  const s = rep.summary;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">
            {rep.role_label}, {rep.kind}
          </p>
          <h1 className="h-display text-4xl">Interview report</h1>
        </div>
        <div className="flex gap-3">
          <Link href="/interview" className="btn bg-xp text-ink hover:bg-[#ffd47a]">
            Run it again
          </Link>
          <Link href="/" className="btn-ghost">
            Hub
          </Link>
        </div>
      </header>

      <section className="panel grid grid-cols-2 gap-6 p-6 md:grid-cols-4">
        <Stat value={s.avg_wpm ?? "–"} label="Words per minute" tone="cyan" />
        <Stat value={s.fillers_per_min ?? "–"} label="Fillers per minute" />
        <Stat value={`${s.long_pauses}`} label="Pauses over 2s" />
        <Stat value={`${s.with_numbers}/${s.answers}`} label="Answers with a number" tone="heal" />
        <p className="col-span-2 text-xs text-muted md:col-span-4">
          Pace and pauses come from {s.voice_answers} spoken answer{s.voice_answers === 1 ? "" : "s"} ({s.speaking_s}s of speech), measured from microphone
          levels. Browser speech recognition often drops “um” and “uh”, so filler counts can run low.
        </p>
      </section>

      {rep.ai_error && <ErrorNote message={rep.ai_error} />}

      {rep.focus.length > 0 && (
        <section className="panel border-xp/40 p-6">
          <h2 className="h-display text-xl">Work on next</h2>
          <ul className="mt-3 list-disc space-y-1.5 pl-5">
            {rep.focus.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </section>
      )}

      <ol className="space-y-5">
        {rep.turns.map((t) => (
          <TurnCard key={t.index} t={t} aiAvailable={rep.ai_available} />
        ))}
      </ol>
    </div>
  );
}
