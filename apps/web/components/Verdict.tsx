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
    <div className="animate-pop space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <p className={`h-display text-3xl ${v.tone}`}>{v.text}</p>
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
      {result.public.length > 0 && (
        <ul className="space-y-2">
          {result.public.map((t) => (
            <li key={t.index} className="rounded-chip border border-line bg-ink/60 p-3 font-mono text-[13px]">
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
