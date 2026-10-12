"use client";

import { FileUp, Play, ShieldCheck, Trophy } from "lucide-react";
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
    <article className="panel grid gap-6 p-6 md:grid-cols-[180px_1fr]">
      <BossArt courseId={course.id} name={course.boss_name} className="mx-auto h-44 w-44" track />
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
            {course.question_types} question types, fresh numbers every time. 15 questions, 5 hearts.
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

function UploadPanel({ onCourse }: { onCourse: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!job || job.status === "succeeded" || job.status === "failed") return;
    const t = setTimeout(async () => {
      try {
        const next = await api.job(job.id);
        setJob(next);
        if (next.status === "succeeded") onCourse();
      } catch (e) {
        setError((e as Error).message);
      }
    }, 1500);
    return () => clearTimeout(t);
  }, [job, onCourse]);

  const pick = (f: File | undefined) => {
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setError("Upload a PDF. Slides and notes can be exported to PDF first.");
      return;
    }
    if (f.size > 25 * 1024 * 1024) {
      setError("That PDF is over 25 MB. Split it and upload the parts.");
      return;
    }
    setError(null);
    setFile(f);
    if (!name) setName(f.name.replace(/\.pdf$/i, "").slice(0, 60));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !name.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setJob(null);
    try {
      const r = await api.uploadCourse(file, name.trim());
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
        Upload lecture slides or notes as a PDF. Reps pulls out the topics, drafts computational questions that quote your material, and keeps only the ones
        that pass verification.
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
            pick(e.dataTransfer.files[0]);
          }}
          className={`flex min-h-[132px] flex-col items-center justify-center gap-2 rounded-panel border-2 border-dashed p-6 text-center transition ${
            drag ? "border-violet bg-violet/10" : "border-line"
          }`}
        >
          <FileUp size={28} className="text-violet-soft" aria-hidden />
          {file ? (
            <p>
              <span className="font-medium">{file.name}</span> <span className="text-muted">({(file.size / 1024 / 1024).toFixed(1)} MB)</span>
            </p>
          ) : (
            <p className="text-muted">Drop a PDF here (text PDFs, up to 25 MB)</p>
          )}
          <button type="button" className="btn-ghost mt-1 px-3 py-1.5 text-sm" onClick={() => input.current?.click()}>
            Choose a file
          </button>
          <input ref={input} type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
        </div>
        <div className="flex flex-col gap-3">
          <div>
            <label htmlFor="course-name" className="label">
              Course name
            </label>
            <input id="course-name" className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="Calc 2, midterm 1" required />
          </div>
          <button type="submit" className="btn-primary mt-auto" disabled={!file || !name.trim() || busy}>
            {busy ? "Reading the PDF" : "Build the boss"}
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
            Read <strong>{result.preview.page_count}</strong> pages ({result.preview.char_count.toLocaleString()} characters) from {result.preview.filename}.
          </p>
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
