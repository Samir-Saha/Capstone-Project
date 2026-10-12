"use client";

import { CheckCircle2, Circle, CircleDot, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, Spinner } from "@/components/ui";
import { api, type ProblemSummary } from "@/lib/api";

const STATUS_ICON = {
  solved: <CheckCircle2 size={20} className="text-cyan" aria-label="Solved" />,
  attempted: <CircleDot size={20} className="text-xp" aria-label="Attempted" />,
  new: <Circle size={20} className="text-line" aria-label="Not started" />,
};

const DIFF_TONE = { easy: "text-heal", medium: "text-xp", hard: "text-hp" };

export default function Arena() {
  const [problems, setProblems] = useState<ProblemSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setProblems(await api.problems());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const solved = problems?.filter((p) => p.status === "solved").length ?? 0;
  const patterns = problems ? [...new Set(problems.map((p) => p.pattern))] : [];

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="h-display text-4xl">Arena</h1>
          <p className="mt-2 max-w-2xl text-muted">
            Original problems grouped by the pattern they train. Run checks the examples; submit runs every hidden test too. Each problem was verified by
            matching a reference solution against an independent brute force on hundreds of random inputs.
          </p>
        </div>
        {problems && (
          <div className="text-right">
            <div className="font-display text-4xl font-bold text-cyan">
              {solved}
              <span className="text-xl text-muted">/{problems.length}</span>
            </div>
            <div className="text-sm text-muted">solved</div>
          </div>
        )}
      </header>
      {error && <ErrorNote message={error} onRetry={load} />}
      {!problems && !error && <Spinner label="Verifying problems (first load takes a moment)" />}
      {problems && (
        <>
          <div className="flex flex-wrap gap-2">
            {patterns.map((p) => {
              const ps = problems.filter((x) => x.pattern === p);
              const done = ps.every((x) => x.status === "solved");
              return (
                <span key={p} className={`chip ${done ? "border-cyan/60 text-cyan" : ""}`}>
                  {p} {ps.filter((x) => x.status === "solved").length}/{ps.length}
                </span>
              );
            })}
          </div>
          <ul className="panel divide-y divide-line">
            {problems.map((p) => (
              <li key={p.slug}>
                <Link
                  href={`/arena/${p.slug}`}
                  className="grid grid-cols-[28px_1fr_auto] items-center gap-4 px-5 py-4 transition-colors hover:bg-raised/60 md:grid-cols-[28px_1fr_160px_90px_110px]"
                >
                  {STATUS_ICON[p.status]}
                  <span className="font-display text-lg font-semibold">{p.title}</span>
                  <span className="hidden text-sm text-muted md:block">{p.pattern}</span>
                  <span className={`hidden text-sm font-semibold capitalize md:block ${DIFF_TONE[p.difficulty]}`}>{p.difficulty}</span>
                  <span className="flex items-center justify-end gap-3 text-sm">
                    <span className="hidden items-center gap-1 text-muted lg:inline-flex" title={`Verified on ${p.verified_cases} cases`}>
                      <ShieldCheck size={14} aria-hidden /> {p.verified_cases}
                    </span>
                    <span className={`font-display font-semibold ${p.status === "solved" ? "text-muted line-through" : "text-xp"}`}>+{p.xp} XP</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
