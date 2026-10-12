"use client";

import { Check, Minus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { TeX } from "@/components/Math";
import { api, type StepReport } from "@/lib/api";

const ROLE: Record<string, string> = {
  problem: "rewrites the problem",
  intermediate: "intermediate result",
  answer: "the answer",
  computation: "computation",
  formula: "formula",
  equation: "same solutions",
};

/** Multi-line work editor with a live rendering of each line. */
export function StepsEditor({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}) {
  const [rendered, setRendered] = useState<{ latex: string | null; error: string | null }[]>([]);
  const lines = value.split("\n");

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        setRendered(await api.previewLines(value.split("\n").slice(0, 20)));
      } catch {
        /* preview is optional */
      }
    }, 300);
    return () => clearTimeout(t);
  }, [value]);

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div>
        <label htmlFor="work" className="label">
          Your work, one step per line. The last line is your answer.
        </label>
        <textarea
          id="work"
          className="field min-h-[150px] font-mono leading-7"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder={"(x-3)(x+3)/(x-3)\nx + 3\n3 + 3 = 6"}
          spellCheck={false}
          disabled={disabled}
        />
      </div>
      <ol className="min-h-[150px] space-y-1 rounded-chip border border-line bg-ink/40 p-3 text-sm" aria-label="How each line was read">
        {lines.map((ln, i) =>
          ln.trim() ? (
            <li key={i} className="flex items-baseline gap-3">
              <span className="w-5 shrink-0 text-right font-mono text-xs text-muted">{i + 1}</span>
              {rendered[i]?.latex ? (
                <TeX tex={rendered[i]!.latex!} />
              ) : (
                <span className="text-muted">{rendered[i]?.error ? `Can't read yet: ${rendered[i]!.error}` : ln}</span>
              )}
            </li>
          ) : null,
        )}
        {!value.trim() && <li className="text-muted">Each line shows up here as Reps reads it.</li>}
      </ol>
    </div>
  );
}

/** Line-by-line verdict on shown work. */
export function StepsView({ report, compact = false }: { report: StepReport; compact?: boolean }) {
  return (
    <div>
      <p className={`text-sm ${report.first_error !== null ? "text-hp" : "text-heal"}`}>{report.summary}</p>
      <ol className="mt-2 space-y-1.5">
        {report.lines.map((ln) => {
          const first = ln.index === report.first_error;
          return (
            <li
              key={ln.index}
              className={`grid grid-cols-[20px_22px_1fr] items-start gap-2 rounded-chip px-2 py-1.5 text-sm ${
                first ? "animate-enter bg-hp/15 ring-1 ring-hp/50" : ""
              }`}
              style={{ animationDelay: `${ln.index * 70}ms` }}
            >
              <span className="pt-0.5 text-right font-mono text-xs text-muted">{ln.index + 1}</span>
              {ln.status === "ok" ? (
                <Check size={16} className="mt-0.5 text-heal" aria-label="Correct step" />
              ) : ln.status === "error" ? (
                <X size={16} className="mt-0.5 text-hp" aria-label="Mistake" />
              ) : (
                <Minus size={16} className="mt-0.5 text-muted" aria-label="Not checked" />
              )}
              <div className="min-w-0">
                <div className="overflow-x-auto">{ln.latex ? <TeX tex={ln.latex} /> : <span className="font-mono">{ln.text}</span>}</div>
                {!compact && ln.status === "ok" && ln.role && <div className="text-xs text-muted">{ROLE[ln.role]}</div>}
                {ln.note && <div className={`text-xs ${ln.status === "error" ? "text-hp" : "text-muted"}`}>{ln.note}</div>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
