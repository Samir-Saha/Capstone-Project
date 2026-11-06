"use client";

import { FileUp, Play, ShieldCheck, Trophy, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { BossArt } from "@/components/BossArt";
import { MasteryBar, SegmentedHp } from "@/components/Hud";
import { ErrorNote, Spinner } from "@/components/ui";
import { api, type Course, type Job, type UploadResult } from "@/lib/api";

function BossCard({ course }: { course: Course }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const fight = await api.startFight(course.id);
      router.push(`/exam/${fight.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <article className="panel group grid gap-6 p-6 transition-shadow duration-200 hover:shadow-lift md:grid-cols-[180px_1fr]">
      <BossArt courseId={course.id} name={course.boss_name} className="mx-auto h-44 w-44 transition-transform duration-300 group-hover:-translate-y-1 group-hover:scale-105" track />
      <div className="min-w-0">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm text-muted">
              {course.name}
              {course.code ? ` (${course.code})` : ""}
              {course.kind === "uploaded" ? ", from your material" : ""}
            </p>
            <h2 className="h-display text-2xl">{course.boss_name}</h2>
          </div>
          <div className="flex items-center gap-4 text-sm text-muted">
            <span className="inline-flex items-center gap-1.5" title="Fights won">
              <Trophy size={15} className="text-xp" aria-hidden /> {course.victories} of {course.fights} won
            </span>
          </div>
        </div>
        <div className="mt-4">
          <SegmentedHp topics={course.topics} hp={course.hp} victoryHp={25} />
        </div>
        {course.ability && (
          <p className="mt-3 text-sm text-muted">
            <span className="font-semibold text-hp">{course.ability.name}.</span> {course.ability.text} Below 50 HP it enters phase 2 and asks harder
            questions.
          </p>
        )}
        <ul className="mt-5 grid gap-x-8 gap-y-2.5 sm:grid-cols-2">
          {course.topics.map((t) => (
            <li key={t.id}>
              <div className="flex justify-between text-sm">
                <span>{t.name}</span>
                {t.attempts > 0 && (
                  <span className="text-muted">
                    {t.correct}/{t.attempts}
                  </span>
                )}
              </div>
              <MasteryBar value={t.mastery} provisional={t.provisional} />
            </li>
          ))}
        </ul>
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <button type="button" className="btn-primary" onClick={start} disabled={busy}>
            <Play size={16} aria-hidden />
            {busy ? "Opening the arena" : course.active_session_id ? "Resume the fight" : "Start the fight"}
          </button>
          <span className="text-sm text-muted">
            {course.from_notes ? `${course.from_notes} questions from your notes${course.question_types > course.from_notes ? `, ${course.question_types - course.from_notes} computed problem types` : ""}` : `${course.question_types} question types, fresh numbers every time`}. 15 questions, 5 hearts.
          </span>
        </div>
        {error && (
          <div className="mt-4">
            <ErrorNote message={error} />
          </div>
        )}
      </div>
    </article>
  );
}

const MAX_FILES = 30;

function UploadPanel({ onCourse }: { onCourse: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [notes, setNotes] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const misses = useRef(0);
  const building = !!job && job.status !== "succeeded" && job.status !== "failed";

  useEffect(() => {
    if (!job || job.status === "succeeded" || job.status === "failed") return;
    const t = setTimeout(async () => {
      try {
        const next = await api.job(job.id);
        misses.current = 0;
        setJob(next);
        if (next.status === "succeeded") {
          onCourse();
          setFiles([]);
          setNotes("");
          setName("");
        }
      } catch (e) {
        // A dropped request shouldn't strand the job: keep polling, give up after ~30 s of failures.
        misses.current += 1;
        if (misses.current >= 20) setError((e as Error).message);
        else setJob({ ...job });
      }
    }, 1500);
    return () => clearTimeout(t);
  }, [job, onCourse]);

  const pick = (list: FileList | null | undefined) => {
    if (!list?.length) return;
    const incoming = Array.from(list);
    const notPdf = incoming.find((f) => !/\.(pdf|txt|md|markdown|docx|pptx)$/i.test(f.name));
    if (notPdf) {
      setError(`${notPdf.name} isn't supported. Use PDF, Word (.docx), PowerPoint (.pptx) or text files, or paste the text below.`);
      return;
    }
    const big = incoming.find((f) => f.size > 25 * 1024 * 1024);
    if (big) {
      setError(`${big.name} is over 25 MB. Split it and upload the parts.`);
      return;
    }
    setError(null);
    setFiles((prev) => {
      const merged = [...prev, ...incoming.filter((f) => !prev.some((p) => p.name === f.name && p.size === f.size))].slice(0, MAX_FILES);
      if (prev.length + incoming.length > MAX_FILES) setError(`Up to ${MAX_FILES} files per boss. The first ${MAX_FILES} are kept.`);
      return merged;
    });
    if (!name) setName(incoming[0]!.name.replace(/\.(pdf|txt|md|markdown|docx|pptx)$/i, "").slice(0, 60));
    if (input.current) input.current.value = "";
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!files.length && !notes.trim()) || !name.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setJob(null);
    try {
      const r = await api.uploadCourse(files, name.trim(), notes);
      setResult(r);
      setJob(r.job);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel p-6" aria-labelledby="upload-title">
      <h2 id="upload-title" className="h-display text-xl">
        Turn your notes into a boss
      </h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Drop in every PDF, slide deck, Word doc or text file for the class, or paste your notes. Each question is built from a sentence in your material and shows the page it came from. With an AI key, Reps also
        writes computational problems and keeps only the ones SymPy verifies.
      </p>
      <form onSubmit={submit} className="mt-5 grid gap-4 md:grid-cols-[1fr_280px]">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            pick(e.dataTransfer.files);
          }}
          className={`flex min-h-[132px] flex-col items-center justify-center gap-2 rounded-panel border-2 border-dashed p-6 text-center transition ${
            drag ? "border-violet bg-violet/10" : "border-line"
          }`}
        >
          <FileUp size={28} className="text-violet-soft" aria-hidden />
          {files.length ? (
            <ul className="w-full max-w-md space-y-1.5 text-left text-sm">
              {files.map((f) => (
                <li key={f.name + f.size} className="flex items-center gap-2 rounded-chip bg-raised/70 px-3 py-1.5">
                  <span className="min-w-0 flex-1 truncate font-medium">{f.name}</span>
                  <span className="shrink-0 text-muted">{(f.size / 1024 / 1024).toFixed(1)} MB</span>
                  <button
                    type="button"
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-chip text-muted hover:bg-line hover:text-text"
                    onClick={() => setFiles((xs) => xs.filter((x) => x !== f))}
                    aria-label={`Remove ${f.name}`}
                  >
                    <X size={14} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">Drop PDFs, slides (.pptx), Word docs (.docx) or text files here (up to {MAX_FILES}, 25 MB each)</p>
          )}
          <button type="button" className="btn-ghost mt-1 px-3 py-1.5 text-sm" onClick={() => input.current?.click()}>
            {files.length ? "Add more files" : "Choose files"}
          </button>
          <input ref={input} type="file" multiple accept="application/pdf,.pdf,.txt,.md,.docx,.pptx,text/plain,text/markdown" className="sr-only" onChange={(e) => pick(e.target.files)} />
          <div className="mt-2 w-full max-w-xl text-left">
            <label htmlFor="paste-notes" className="label">
              Or paste notes
            </label>
            <textarea
              id="paste-notes"
              className="field min-h-[120px] resize-y text-sm"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Paste a study guide, lecture notes, or anything with full sentences. Headings become topics."
            />
            {notes.trim() && <p className="mt-1 text-xs text-muted">{notes.trim().split(/\s+/).length.toLocaleString()} words</p>}
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <div>
            <label htmlFor="course-name" className="label">
              Course name
            </label>
            <input id="course-name" className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="Calc 2, midterm 1" required />
          </div>
          <button type="submit" className="btn-primary mt-auto" disabled={(!files.length && !notes.trim()) || !name.trim() || busy || building}>
            {busy ? "Reading your notes" : building ? "Building" : "Build the boss"}
          </button>
        </div>
      </form>
      {error && (
        <div className="mt-4">
          <ErrorNote message={error} />
        </div>
      )}
      {result && (
        <div className="mt-5 rounded-chip border border-line bg-ink/60 p-4 text-sm">
          <p>
            Read <strong>{result.preview.page_count}</strong> pages ({result.preview.char_count.toLocaleString()} characters) from {result.preview.filename}
            {result.preview.files && result.preview.files.length > 1 && <span className="text-muted">: {result.preview.files.map((f) => `${f.name} (${f.pages} pp.)`).join(", ")}</span>}.
          </p>
          {result.preview.skipped && result.preview.skipped.length > 0 && (
            <ul className="mt-2 space-y-1 text-xp">
              {result.preview.skipped.map((f) => (
                <li key={f.name}>
                  Skipped {f.name}: {f.reason}
                </li>
              ))}
            </ul>
          )}
          {result.preview.sample[0] && (
            <blockquote className="mt-3 border-l-2 border-violet/60 pl-3 text-muted">
              <span className="block text-xs">Page {result.preview.sample[0].pages[0]}</span>
              {result.preview.sample[0].text}…
            </blockquote>
          )}
          <p className={`mt-3 ${result.ai_available ? "text-text" : "text-xp"}`}>{result.message}</p>
          {job && (
            <div className="mt-3 flex items-center gap-3">
              {job.status === "succeeded" ? (
                <span className="inline-flex items-center gap-2 text-heal">
                  <ShieldCheck size={16} aria-hidden /> {job.result?.message} Your new boss is above.
                </span>
              ) : job.status === "failed" ? (
                <span className="text-hp">{job.error}</span>
              ) : (
                <Spinner label={job.progress.message ?? "Working"} />
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default function ExamHome() {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setCourses(await api.courses());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="h-display text-4xl">Boss fights</h1>
        <p className="mt-2 max-w-2xl text-muted">
          Each boss is a course. Its HP is your gap to mastery across every topic, so the only way to win is to actually learn the material. Get it to 25 HP or
          lower before your hearts run out.
        </p>
      </header>
      {error && <ErrorNote message={error} onRetry={load} />}
      {!courses && !error && <Spinner label="Summoning bosses" />}
      {courses?.map((c) => <BossCard key={c.id} course={c} />)}
      <UploadPanel onCourse={load} />
    </div>
  );
}
