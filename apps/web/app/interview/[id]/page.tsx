"use client";

import { Keyboard, Mic, Square, Volume2, VolumeX } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CodeEditor } from "@/components/CodeEditor";
import { ErrorNote, Spinner } from "@/components/ui";
import { api, notifyProgress, type AudioMetrics, type InterviewState, type Turn } from "@/lib/api";
import { speak, stopSpeaking, useRecorder, voiceSupport } from "@/lib/voice";

const SOURCE_LABEL: Record<string, string> = {
  behavioral: "Behavioral",
  resume: "From your resume",
  follow_up: "Follow-up",
  technical: "Coding",
};

const VOICE_KEY = "reps.interviewer-voice";

function Interviewer({ speaking }: { speaking: boolean }) {
  return (
    <div className="relative mx-auto h-36 w-36" aria-hidden>
      {speaking && <span className="absolute inset-0 animate-pulse_ring rounded-full border-2 border-xp" />}
      <svg viewBox="0 0 120 120" className="h-full w-full">
        <defs>
          <radialGradient id="iv" cx="40%" cy="35%" r="70%">
            <stop offset="0%" stopColor="#FFF4D6" />
            <stop offset="45%" stopColor="#FFC857" />
            <stop offset="100%" stopColor="#7A4E0A" />
          </radialGradient>
        </defs>
        <circle cx="60" cy="60" r="44" fill="url(#iv)" />
        <circle cx="60" cy="60" r="52" fill="none" stroke="#FFC857" strokeOpacity="0.35" strokeWidth="1.5" strokeDasharray="4 6" />
        {[0, 1, 2, 3, 4].map((i) => (
          <rect
            key={i}
            x={41 + i * 8}
            width="5"
            rx="2.5"
            fill="#2A1B04"
            y={speaking ? 52 - ((i * 7) % 11) : 57}
            height={speaking ? 16 + ((i * 7) % 11) * 2 : 6}
            style={{ transition: "all 200ms" }}
          />
        ))}
      </svg>
    </div>
  );
}

function LevelMeter({ level }: { level: number }) {
  return (
    <div className="flex h-10 items-end gap-1" aria-hidden>
      {Array.from({ length: 24 }, (_, i) => {
        const on = level * 24 > i;
        return <span key={i} className={`w-1.5 rounded-sm transition-all duration-75 ${on ? "bg-xp" : "bg-line"}`} style={{ height: `${20 + ((i * 37) % 80)}%` }} />;
      })}
    </div>
  );
}

function fmtTime(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

export default function Room() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [state, setState] = useState<InterviewState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"voice" | "text">("voice");
  const [text, setText] = useState("");
  const [code, setCode] = useState("");
  const [captured, setCaptured] = useState<{ transcript: string; audio: AudioMetrics } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [last, setLast] = useState<{ turn: Turn; followUp: string | null } | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [voiceOn, setVoiceOn] = useState(true);
  const [support, setSupport] = useState({ transcript: false, microphone: false, speech: false });
  const recorder = useRecorder();

  const say = useCallback(
    (t: string) => {
      if (!voiceOn) return;
      setSpeaking(true);
      speak(t, () => setSpeaking(false));
    },
    [voiceOn],
  );

  const load = useCallback(async () => {
    try {
      const s = await api.interview(id);
      if (s.status === "completed") {
        router.replace(`/interview/${id}/report`);
        return;
      }
      setState(s);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id, router]);

  useEffect(() => {
    const sup = voiceSupport();
    setSupport(sup);
    if (!sup.microphone || !sup.transcript) setMode("text");
    try {
      setVoiceOn(localStorage.getItem(VOICE_KEY) !== "off");
    } catch {
      /* default on */
    }
    void load();
    return () => stopSpeaking();
  }, [load]);

  const q = state?.question ?? null;

  useEffect(() => {
    if (!q) return;
    setText("");
    setCaptured(null);
    setCode(q.problem?.starter_code ?? "");
    const t = setTimeout(() => say(q.text), 300);
    return () => clearTimeout(t);
  }, [q?.index, q?.text]);

  const toggleVoice = () => {
    const next = !voiceOn;
    setVoiceOn(next);
    if (!next) {
      stopSpeaking();
      setSpeaking(false);
    }
    try {
      localStorage.setItem(VOICE_KEY, next ? "on" : "off");
    } catch {
      /* not remembered */
    }
  };

  const startRecording = async () => {
    stopSpeaking();
    setSpeaking(false);
    setCaptured(null);
    await recorder.start();
  };

  const stopRecording = () => {
    const out = recorder.stop();
    setCaptured(out);
    setText(out.transcript);
  };

  const submit = async () => {
    if (!q || !state) return;
    const transcript = text.trim();
    if (!transcript && !(q.kind === "technical" && code.trim())) return;
    setSubmitting(true);
    setError(null);
    try {
      const out = await api.interviewAnswer(id, {
        index: q.index,
        transcript,
        input_mode: mode === "voice" && captured ? "voice" : "text",
        audio: mode === "voice" && captured ? captured.audio : undefined,
        code: q.kind === "technical" ? code : undefined,
      });
      setLast({ turn: out.turn, followUp: out.follow_up_added });
      notifyProgress(out.xp);
      setState(out.session);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const finish = async () => {
    setSubmitting(true);
    try {
      const rep = await api.finishInterview(id);
      notifyProgress(rep.xp ?? 0);
      router.push(`/interview/${id}/report`);
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  };

  if (error && !state) return <ErrorNote message={error} onRetry={load} />;
  if (!state) return <Spinner label="Opening the interview room" />;

  // Show the last answer's measurements until the next answer begins.
  const between = last !== null && !recorder.recording && !text && !captured;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)]">
      {/* Interviewer */}
      <section className="panel flex flex-col p-6" aria-label="Interviewer">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted">{state.role_label}</span>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 text-muted hover:text-text"
            onClick={toggleVoice}
            aria-pressed={voiceOn}
            disabled={!support.speech}
          >
            {voiceOn ? <Volume2 size={16} aria-hidden /> : <VolumeX size={16} aria-hidden />} Interviewer voice {voiceOn ? "on" : "off"}
          </button>
        </div>
        <div className="mt-6">
          <Interviewer speaking={speaking} />
        </div>
        <div className="mt-6 flex items-center gap-1.5" aria-label={`${state.answered} of ${state.total} answered`}>
          {Array.from({ length: state.total }, (_, i) => (
            <span key={i} className={`h-1.5 flex-1 rounded-full ${i < state.answered ? "bg-xp" : i === state.answered ? "bg-xp/40" : "bg-line"}`} />
          ))}
        </div>
        {q ? (
          <div className="mt-6" aria-live="polite">
            <span className={`chip ${q.kind === "follow_up" ? "border-xp/60 text-xp" : ""}`}>{SOURCE_LABEL[q.kind]}</span>
            <p className="mt-3 font-display text-xl leading-snug">{q.text}</p>
            {voiceOn && (
              <button type="button" className="mt-3 text-sm text-muted hover:text-text" onClick={() => say(q.text)}>
                Repeat the question
              </button>
            )}
          </div>
        ) : (
          <div className="mt-6">
            <p className="font-display text-xl">That's every question.</p>
            <p className="mt-2 text-sm text-muted">Finish to see your measured results{state.ai_feedback_available ? " and AI STAR scores" : ""}.</p>
          </div>
        )}
        <div className="mt-auto pt-6 text-xs text-muted">
          Question {Math.min(state.answered + 1, state.total)} of {state.total}. Vague answers can earn a follow-up.
        </div>
      </section>

      {/* Answer */}
      <section className="panel flex min-h-[560px] flex-col p-6" aria-label="Your answer">
        {last && between && (
          <div className="mb-6 animate-pop rounded-panel border border-line bg-ink/60 p-4 text-sm" role="status">
            <p className="font-display font-semibold">Answer recorded</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="chip">{last.turn.metrics.words} words</span>
              {last.turn.metrics.wpm ? <span className="chip">{last.turn.metrics.wpm} wpm</span> : null}
              {last.turn.metrics.pause_count !== undefined && <span className="chip">{last.turn.metrics.pause_count} pauses</span>}
              <span className="chip">{last.turn.metrics.filler_total} fillers</span>
              <span className={`chip ${last.turn.checks.mentions_number ? "border-heal/50 text-heal" : ""}`}>
                {last.turn.checks.mentions_number ? "Has a number" : "No numbers"}
              </span>
              {last.turn.checks.code && <span className="chip">Code: {last.turn.checks.code.verdict.replace(/_/g, " ")}</span>}
            </div>
            {last.followUp && <p className="mt-3 text-xp">The interviewer wants to dig into that answer.</p>}
          </div>
        )}

        {!q ? (
          <div className="m-auto text-center">
            <button type="button" className="btn bg-xp px-8 py-3 text-lg text-ink hover:bg-[#ffd47a]" onClick={finish} disabled={submitting}>
              {submitting ? "Scoring" : "Finish and see the report"}
            </button>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <h2 className="h-display text-lg">Your answer</h2>
              <div className="flex rounded-chip border border-line p-0.5 text-sm" role="tablist" aria-label="Answer mode">
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === "voice"}
                  disabled={!support.microphone || !support.transcript || recorder.recording}
                  onClick={() => setMode("voice")}
                  className={`inline-flex items-center gap-1.5 rounded px-3 py-1 ${mode === "voice" ? "bg-raised text-text" : "text-muted"}`}
                >
                  <Mic size={14} aria-hidden /> Speak
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === "text"}
                  disabled={recorder.recording}
                  onClick={() => setMode("text")}
                  className={`inline-flex items-center gap-1.5 rounded px-3 py-1 ${mode === "text" ? "bg-raised text-text" : "text-muted"}`}
                >
                  <Keyboard size={14} aria-hidden /> Type
                </button>
              </div>
            </div>
            {(!support.microphone || !support.transcript) && (
              <p className="mt-2 text-xs text-muted">Speaking needs Chrome or Edge with a microphone. Typing works everywhere, but pace and pauses won't be measured.</p>
            )}

            {q.kind === "technical" && q.problem && (
              <div className="mt-4 overflow-hidden rounded-panel border border-line">
                <div className="border-b border-line bg-ink/60 px-4 py-2 text-sm">
                  <span className="font-semibold">{q.problem.title}</span>
                  <span className="ml-2 text-muted">{q.problem.statement}</span>
                </div>
                <div className="h-56">
                  <CodeEditor value={code} onChange={setCode} label={`Interview solution for ${q.problem.title}`} />
                </div>
              </div>
            )}

            {mode === "voice" ? (
              <div className="mt-5 flex flex-1 flex-col">
                <div className="flex items-center gap-5">
                  {recorder.recording ? (
                    <button type="button" onClick={stopRecording} className="btn bg-hp px-6 py-3 text-white hover:bg-[#ff7590]">
                      <Square size={16} className="fill-white" aria-hidden /> Stop
                    </button>
                  ) : (
                    <button type="button" onClick={startRecording} className="btn bg-xp px-6 py-3 text-ink hover:bg-[#ffd47a]">
                      <Mic size={18} aria-hidden /> {captured ? "Record again" : "Start answering"}
                    </button>
                  )}
                  {recorder.recording && (
                    <>
                      <LevelMeter level={recorder.level} />
                      <span className="font-display text-xl tabular-nums">{fmtTime(recorder.elapsed)}</span>
                    </>
                  )}
                </div>
                {recorder.error && (
                  <div className="mt-4">
                    <ErrorNote message={recorder.error} />
                  </div>
                )}
                <div className="mt-5 flex-1">
                  {recorder.recording ? (
                    <p className="min-h-[160px] rounded-panel border border-line bg-ink/50 p-4 leading-relaxed" aria-live="polite">
                      {recorder.transcript} <span className="text-muted">{recorder.interim}</span>
                      {!recorder.transcript && !recorder.interim && <span className="text-muted">Listening…</span>}
                    </p>
                  ) : captured ? (
                    <>
                      <label htmlFor="transcript" className="label">
                        Transcript (fix anything it misheard; your timing is already measured)
                      </label>
                      <textarea id="transcript" className="field min-h-[160px] leading-relaxed" value={text} onChange={(e) => setText(e.target.value)} />
                      <p className="mt-2 text-xs text-muted">
                        {captured.audio.speaking_s}s of speech, {captured.audio.pauses_ms.filter((p) => p >= 600).length} pauses over 0.6s.
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-muted">
                      Press start, answer out loud, then stop. Aim for 1 to 2 minutes: situation, task, what you did, and the result with a number.
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="mt-5 flex-1">
                <label htmlFor="typed" className="label">
                  {q.kind === "technical" ? "Explain your approach and its complexity" : "Type your answer"}
                </label>
                <textarea
                  id="typed"
                  className="field min-h-[200px] leading-relaxed"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Situation, task, what you did, and the result."
                />
              </div>
            )}

            {error && (
              <div className="mt-4">
                <ErrorNote message={error} />
              </div>
            )}
            <div className="mt-5 flex items-center justify-between gap-4 border-t border-line pt-4">
              <button type="button" className="text-sm text-muted hover:text-text" onClick={finish} disabled={submitting || state.answered === 0}>
                End early
              </button>
              <button
                type="button"
                className="btn bg-xp px-6 text-ink hover:bg-[#ffd47a]"
                onClick={submit}
                disabled={submitting || recorder.recording || (!text.trim() && !(q.kind === "technical" && code.trim()))}
              >
                {submitting ? "Saving" : "Submit answer"}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
