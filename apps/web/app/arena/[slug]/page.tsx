"use client";

import { ArrowLeft, Play, RotateCcw, Send, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CodeEditor } from "@/components/CodeEditor";
import { VerdictView } from "@/components/Verdict";
import { ErrorNote, Spinner } from "@/components/ui";
import { api, notifyProgress, type CodeResult, type ProblemDetail } from "@/lib/api";
import { play } from "@/lib/sound";

const draftKey = (slug: string) => `reps.draft.${slug}`;

function readDraft(slug: string) {
  try {
    return localStorage.getItem(draftKey(slug));
  } catch {
    return null;
  }
}

export default function ProblemPage() {
  const { slug } = useParams<{ slug: string }>();
  const [problem, setProblem] = useState<ProblemDetail | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"run" | "submit" | null>(null);
  const [result, setResult] = useState<{ mode: "run" | "submit"; data: CodeResult } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const p = await api.problem(slug);
      setProblem(p);
      setCode(readDraft(slug) ?? p.saved_code ?? p.starter_code);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [slug]);
  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!problem) return;
    const t = setTimeout(() => {
      try {
        localStorage.setItem(draftKey(slug), code);
      } catch {
        /* drafts are a convenience */
      }
    }, 400);
    return () => clearTimeout(t);
  }, [code, slug, problem]);

  const go = useCallback(
    async (mode: "run" | "submit") => {
      if (busy || !code.trim()) return;
      setBusy(mode);
      setError(null);
      try {
        const data = mode === "run" ? await api.run(slug, code) : await api.submit(slug, code);
        setResult({ mode, data });
        play(data.verdict === "accepted" ? "accepted" : "rejected");
        if (mode === "submit") {
          notifyProgress(data.xp);
          setProblem((p) => (p ? { ...p, status: data.status } : p));
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(null);
      }
    },
    [busy, code, slug],
  );

  if (error && !problem) return <ErrorNote message={error} onRetry={load} />;
  if (!problem) return <Spinner label="Loading the problem" />;

  return (
    <div className="grid gap-5 lg:h-[calc(100vh-7.5rem)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      {/* Statement */}
      <section className="panel flex min-h-0 flex-col overflow-hidden">
        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          <Link href="/arena" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-text">
            <ArrowLeft size={15} aria-hidden /> Arena
          </Link>
          <h1 className="h-display mt-3 text-3xl">{problem.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="chip border-cyan/50 text-cyan">{problem.pattern}</span>
            <span className="chip capitalize">{problem.difficulty}</span>
            <span className="chip">{problem.status === "solved" ? "Solved" : `+${problem.xp} XP on first solve`}</span>
          </div>
          <p className="mt-6 text-[15px] leading-relaxed">{problem.statement}</p>
          <pre className="mt-5 overflow-x-auto rounded-chip border border-line bg-ink/70 px-4 py-3 font-mono text-[13px] text-cyan">{problem.signature}</pre>
          <h2 className="h-display mt-7 text-lg">Examples</h2>
          <ul className="mt-3 space-y-3">
            {problem.examples.map((ex, i) => (
              <li key={i} className="rounded-chip border border-line bg-ink/50 p-3 font-mono text-[13px]">
                <div>
                  <span className="text-muted">solve(</span>
                  {ex.args.map((a) => JSON.stringify(a)).join(", ")}
                  <span className="text-muted">)</span>
                </div>
                <div className="mt-1">
                  <span className="text-muted">returns </span>
                  {JSON.stringify(ex.expected)}
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-6 flex items-start gap-2 text-sm text-muted">
            <ShieldCheck size={16} className="mt-0.5 shrink-0 text-heal" aria-hidden />
            Submit also runs {problem.hidden_tests} hidden tests. This problem passed {problem.verification.cases_run} differential checks before it was
            published.
          </p>
          {problem.history.length > 0 && (
            <>
              <h2 className="h-display mt-7 text-lg">Your attempts</h2>
              <ul className="mt-2 divide-y divide-line text-sm">
                {problem.history.map((h, i) => (
                  <li key={i} className="flex justify-between py-2">
                    <span className={h.verdict === "accepted" ? "text-cyan" : "text-muted"}>
                      {h.is_submit ? "Submit" : "Run"}: {h.verdict.replace(/_/g, " ")}
                    </span>
                    <span className="tabular-nums text-muted">
                      {h.passed}/{h.total}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </section>

      {/* Editor and console */}
      <section className="flex min-h-[640px] flex-col gap-5 lg:min-h-0">
        <div className="panel flex min-h-[340px] flex-1 flex-col overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
            <span className="font-mono text-sm text-muted">Python 3</span>
            <button
              type="button"
              className="ml-2 inline-flex items-center gap-1 text-sm text-muted hover:text-text"
              onClick={() => setCode(problem.starter_code)}
              title="Reset to the starter code"
            >
              <RotateCcw size={14} aria-hidden /> Reset
            </button>
            <div className="ml-auto flex gap-2">
              <button type="button" className="btn-ghost py-1.5" onClick={() => go("run")} disabled={!!busy}>
                <Play size={15} aria-hidden /> {busy === "run" ? "Running" : "Run"}
                <span className="kbd">Ctrl+Enter</span>
              </button>
              <button type="button" className="btn-cyan py-1.5" onClick={() => go("submit")} disabled={!!busy}>
                <Send size={15} aria-hidden /> {busy === "submit" ? "Judging" : "Submit"}
                <span className="kbd hidden xl:inline">Ctrl+Shift+Enter</span>
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1">
            <CodeEditor value={code} onChange={setCode} onRun={() => go("run")} onSubmit={() => go("submit")} label={`Solution for ${problem.title}`} />
          </div>
        </div>
        <div className="panel max-h-[45%] min-h-[150px] overflow-y-auto p-5" aria-live="polite">
          {error && <ErrorNote message={error} />}
          {busy ? (
            <Spinner label={busy === "run" ? "Running the examples" : "Running every test"} />
          ) : result ? (
            <VerdictView result={result.data} mode={result.mode} />
          ) : (
            <p className="text-sm text-muted">Run your code to check the examples. Submit when you think it handles everything.</p>
          )}
        </div>
      </section>
    </div>
  );
}
