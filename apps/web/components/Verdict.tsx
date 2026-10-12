"use client";

import { Check, X } from "lucide-react";
import type { CodeResult } from "@/lib/api";

const LABEL: Record<CodeResult["verdict"], { text: string; tone: string }> = {
  accepted: { text: "Accepted", tone: "text-cyan" },
  wrong_answer: { text: "Wrong answer", tone: "text-hp" },
  compilation_error: { text: "Syntax error", tone: "text-hp" },
  runtime_error: { text: "Runtime error", tone: "text-hp" },
  time_limit_exceeded: { text: "Too slow", tone: "text-xp" },
  memory_limit_exceeded: { text: "Out of memory", tone: "text-xp" },
  execution_unavailable: { text: "Runner offline", tone: "text-muted" },
};

const fmt = (v: unknown) => JSON.stringify(v);

export function VerdictView({ result, mode }: { result: CodeResult; mode: "run" | "submit" }) {
  const v = LABEL[result.verdict];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <p
          className={`h-display animate-stamp text-3xl ${v.tone} ${
            result.verdict === "accepted" ? "drop-shadow-[0_0_18px_rgba(63,216,230,0.55)]" : ""
          }`}
        >
          {v.text}
        </p>
        <p className="text-sm text-muted">
          {result.passed}/{result.total} tests passed
          {mode === "submit" && result.hidden_total > 0 && ` (${result.hidden_passed}/${result.hidden_total} hidden)`}
          {result.runtime_ms !== null && `, ${result.runtime_ms.toFixed(1)} ms total`}
        </p>
        {result.xp > 0 && <p className="font-display font-semibold text-xp">+{result.xp} XP</p>}
      </div>
      {result.verdict === "time_limit_exceeded" && <p className="text-sm">Your code ran past the time limit. Look for an infinite loop or a faster approach.</p>}
      {result.error && <pre className="whitespace-pre-wrap rounded-chip bg-hp/10 p-3 font-mono text-[13px] text-hp">{result.error}</pre>}
      {result.first_failed_hidden !== null && (
        <p className="text-sm text-muted">
          First failure: hidden test {result.first_failed_hidden}. Hidden inputs stay hidden, so think about edge cases: empty input, duplicates, negatives.
        </p>
      )}
      {mode === "submit" && result.hidden_total > 0 && (
        <div>
          <div className="flex justify-between text-xs text-muted">
            <span>Hidden tests</span>
            <span className="tabular-nums">
              {result.hidden_passed}/{result.hidden_total}
            </span>
          </div>
          {/* One tick per hidden test, passes first. Hidden results are counts, not positions. */}
          <div className="mt-1.5 flex gap-[2px]" aria-hidden>
            {Array.from({ length: result.hidden_total }, (_, i) => (
              <span
                key={i}
                className={`h-2.5 flex-1 animate-enter rounded-sm ${
                  i < result.hidden_passed ? "bg-cyan" : result.verdict === "wrong_answer" ? "bg-hp" : "bg-line"
                }`}
                style={{ animationDelay: `${i * 18}ms` }}
              />
            ))}
          </div>
        </div>
      )}
      {result.public.length > 0 && (
        <ul className="space-y-2">
          {result.public.map((t, i) => (
            <li key={t.index} className="animate-enter rounded-chip border border-line bg-ink/60 p-3 font-mono text-[13px]" style={{ animationDelay: `${120 + i * 90}ms` }}>
              <div className="mb-1 flex items-center gap-2 font-sans text-xs">
                {t.passed ? <Check size={14} className="text-cyan" aria-hidden /> : <X size={14} className="text-hp" aria-hidden />}
                <span className={t.passed ? "text-cyan" : "text-hp"}>Example {t.index}</span>
              </div>
              <div className="text-muted">
                solve({t.args.map(fmt).join(", ")})
              </div>
              <div>
                <span className="text-muted">expected </span>
                {fmt(t.expected)}
                <span className="ml-4 text-muted">got </span>
                <span className={t.passed ? "" : "text-hp"}>{t.output === null ? "nothing" : fmt(t.output)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted">
        Ran on {result.executor === "judge0" ? "Judge0" : "the local runner"}. Graded by comparing outputs, not by AI.
      </p>
    </div>
  );
}
