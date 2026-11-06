"use client";

import { BrainCircuit, Briefcase, Code2, FileUp, LineChart, Mic, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ErrorNote, timeAgo } from "@/components/ui";
import { api, type InterviewHistoryItem, type Resume } from "@/lib/api";

const ROLES = [
  { id: "software", label: "Software engineering", icon: Code2 },
  { id: "quant", label: "Quant and trading", icon: LineChart },
  { id: "ai_ml", label: "AI and machine learning", icon: BrainCircuit },
  { id: "general", label: "General internship", icon: Briefcase },
];

const KINDS = [
  { id: "intro", label: "Tell me about yourself", note: "One 60–90 second pitch, graded on a 7-point rubric" },
  { id: "behavioral", label: "Behavioral", note: "STAR stories, resume follow-ups" },
  { id: "mixed", label: "Mixed", note: "Behavioral plus one coding question" },
  { id: "technical", label: "Technical", note: "Coding questions you talk through" },
];

export default function InterviewSetup() {
  const router = useRouter();
  const [role, setRole] = useState("software");
  const [kind, setKind] = useState("behavioral");
  const [length, setLength] = useState(4);
  const [resume, setResume] = useState<Resume | null>(null);
  const [useResume, setUseResume] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<InterviewHistoryItem[]>([]);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.latestResume().then(setResume).catch(() => undefined);
    api.interviews().then(setHistory).catch(() => undefined);
  }, []);

  const upload = async (f: File | undefined) => {
    if (!f) return;
    setUploading(true);
    setError(null);
    try {
      setResume(await api.uploadResume(f));
      setUseResume(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const s = await api.startInterview({ role, kind, length, resume_id: useResume && resume ? resume.id : null });
      router.push(`/interview/${s.id}`);
    } catch (e) {
      setError((e as Error).message);
      setStarting(false);
    }
  };

  const measurable = resume?.claims.filter((c) => c.measurable) ?? [];

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,7fr)_minmax(0,4fr)]">
      <div className="space-y-8">
        <header>
          <h1 className="h-display text-4xl">Gauntlet</h1>
          <p className="mt-2 max-w-2xl text-muted">
            A mock interview you answer out loud. Reps measures your pace and pauses from the microphone, counts filler words, and presses you on the
            claims in your resume.
          </p>
        </header>

        <fieldset>
          <legend className="h-display mb-3 text-lg">Role</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {ROLES.map(({ id, label, icon: Icon }) => (
              <label
                key={id}
                className={`flex cursor-pointer items-center gap-3 rounded-panel border p-4 transition ${
                  role === id ? "border-sun bg-sun/[0.14] shadow-lift ring-2 ring-sun/40" : "border-line bg-surface shadow-card hover:-translate-y-0.5 hover:border-sun hover:shadow-lift"
                }`}
              >
                <input type="radio" name="role" value={id} checked={role === id} onChange={() => setRole(id)} className="sr-only" />
                <Icon size={20} className={role === id ? "text-xp" : "text-muted"} aria-hidden />
                <span className="font-display font-semibold">{label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="h-display mb-3 text-lg">Format</legend>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {KINDS.map((k) => (
              <label
                key={k.id}
                className={`cursor-pointer rounded-panel border p-4 transition ${kind === k.id ? "border-sun bg-sun/[0.14] shadow-lift ring-2 ring-sun/40" : "border-line bg-surface shadow-card hover:-translate-y-0.5 hover:border-sun hover:shadow-lift"}`}
              >
                <input type="radio" name="kind" value={k.id} checked={kind === k.id} onChange={() => setKind(k.id)} className="sr-only" />
                <div className="font-display font-semibold">{k.label}</div>
                <div className="mt-1 text-sm text-muted">{k.note}</div>
              </label>
            ))}
          </div>
          {kind !== "technical" && kind !== "intro" && (
            <div className="mt-4 flex items-center gap-4">
              <label htmlFor="length" className="text-sm text-muted">
                Questions
              </label>
              <input id="length" type="range" min={2} max={6} value={length} onChange={(e) => setLength(Number(e.target.value))} className="w-48 accent-[#8B5CF6]" />
              <span className="font-display font-semibold tabular-nums">{length}</span>
              <span className="text-sm text-muted">plus up to 2 follow-ups</span>
            </div>
          )}
        </fieldset>

        <section className="panel p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="h-display text-lg">Resume</h2>
              <p className="mt-1 text-sm text-muted">Optional. Reps picks out your claims with numbers in them and asks you to back them up.</p>
            </div>
            <button type="button" className="btn-ghost" onClick={() => input.current?.click()} disabled={uploading}>
              <FileUp size={16} aria-hidden /> {uploading ? "Reading" : resume ? "Replace PDF" : "Upload PDF"}
            </button>
            <input ref={input} type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} />
          </div>
          {!pasting ? (
            <button type="button" className="mt-3 text-sm text-muted underline-offset-4 hover:text-text hover:underline" onClick={() => setPasting(true)}>
              No PDF handy? Paste your resume text instead
            </button>
          ) : (
            <div className="mt-4">
              <label htmlFor="resume-text" className="label">
                Resume text
              </label>
              <textarea
                id="resume-text"
                className="field min-h-[140px] resize-y text-sm"
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
                placeholder="Paste everything: experience, projects, skills. One bullet per line works best."
              />
              <div className="mt-2 flex gap-3">
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={uploading || pasted.trim().length < 80}
                  onClick={async () => {
                    setUploading(true);
                    setError(null);
                    try {
                      setResume(await api.pasteResume(pasted));
                      setUseResume(true);
                      setPasting(false);
                      setPasted("");
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setUploading(false);
                    }
                  }}
                >
                  {uploading ? "Reading" : "Use this resume"}
                </button>
                <button type="button" className="text-sm text-muted hover:text-text" onClick={() => setPasting(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
          {resume && (
            <div className="mt-5">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={useResume} onChange={(e) => setUseResume(e.target.checked)} className="accent-[#8B5CF6]" />
                Use {resume.filename} ({resume.claims.length} claims found, {measurable.length} with numbers)
              </label>
              {resume.review && resume.review.total > 0 ? (
                <div className="mt-4">
                  <div className="flex items-baseline justify-between gap-3">
                    <h3 className="font-display text-base font-semibold">Resume check</h3>
                    <span className="text-sm text-muted">
                      <span className={`font-semibold tabular-nums ${resume.review.ready === resume.review.total ? "text-heal" : "text-text"}`}>
                        {resume.review.ready}/{resume.review.total}
                      </span>{" "}
                      lines interview-ready
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised" aria-hidden>
                    <div className="h-full rounded-full bg-heal transition-[width] duration-700" style={{ width: `${(100 * resume.review.ready) / resume.review.total}%` }} />
                  </div>
                  <ul className="mt-3 max-h-[340px] space-y-2 overflow-y-auto pr-1 text-sm">
                    {[...resume.review.items]
                      .sort((a, b) => Number(a.ready) - Number(b.ready))
                      .map((item, i) => (
                        <li key={i} className={`rounded-chip border px-3 py-2.5 ${item.ready ? "border-heal/30 bg-heal/[0.05]" : "border-line bg-surface"}`}>
                          <p className="text-text">{item.text}</p>
                          {item.strengths.length > 0 && (
                            <div className="mt-1.5 flex flex-wrap gap-1.5">
                              {item.strengths.map((s) => (
                                <span key={s} className="rounded-full bg-heal/10 px-2 py-0.5 text-xs text-heal">
                                  {s}
                                </span>
                              ))}
                            </div>
                          )}
                          {item.fixes.map((f) => (
                            <p key={f} className="mt-1.5 text-xs text-muted">
                              <span className="font-semibold text-xp">Fix: </span>
                              {f}
                            </p>
                          ))}
                        </li>
                      ))}
                  </ul>
                </div>
              ) : (
                measurable.length > 0 && (
                  <ul className="mt-3 space-y-2 text-sm">
                    {measurable.slice(0, 4).map((c, i) => (
                      <li key={i} className="rounded-chip border border-line bg-ink/50 px-3 py-2">
                        {c.text}
                      </li>
                    ))}
                  </ul>
                )
              )}
              <p className="mt-3 text-xs text-muted">
                Checked with simple rules (numbers, outcomes, opening verbs), not AI. The Gauntlet presses hardest on lines with numbers.
              </p>
            </div>
          )}
        </section>

        {error && <ErrorNote message={error} />}
        <button type="button" className="btn-sun w-full py-3.5 text-lg sm:w-auto sm:px-10" onClick={start} disabled={starting}>
          <Mic size={18} aria-hidden /> {starting ? "Setting up the room" : "Enter the room"}
        </button>
      </div>

      <aside className="space-y-6">
        <div className="panel p-6">
          <h2 className="h-display text-lg">What gets measured</h2>
          <ul className="mt-3 space-y-2.5 text-sm text-muted">
            <li>
              <span className="text-text">Pace and pauses</span> come from your microphone's audio levels.
            </li>
            <li>
              <span className="text-text">Filler words and structure checks</span> are counted from the transcript.
            </li>
            <li>
              <span className="text-text">Code</span> runs against the same hidden tests as the Arena.
            </li>
            <li>
              <span className="text-text">STAR scores</span> need an AI key and are always labeled as AI judgment.
            </li>
          </ul>
          <p className="mt-4 text-xs text-muted">Voice works best in Chrome or Edge. You can always type instead.</p>
        </div>
        {history.length > 0 && (
          <div className="panel p-6">
            <h2 className="h-display flex items-center gap-2 text-lg">
              <Users size={18} aria-hidden /> Past interviews
            </h2>
            <ul className="mt-3 divide-y divide-line text-sm">
              {history.map((h) => (
                <li key={h.id}>
                  <Link
                    href={h.status === "completed" ? `/interview/${h.id}/report` : `/interview/${h.id}`}
                    className="flex justify-between py-2.5 hover:text-xp"
                  >
                    <span>
                      {ROLES.find((r) => r.id === h.role)?.label ?? h.role}, {h.kind}
                    </span>
                    <span className="text-muted">{h.status === "completed" ? timeAgo(h.started_at) : "Unfinished"}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}
