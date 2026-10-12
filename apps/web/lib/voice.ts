"use client";

// Voice for the Gauntlet, built on browser APIs (no paid provider needed):
//   - transcript: Web Speech API (Chrome and Edge on Windows support it)
//   - delivery metrics: measured from microphone audio levels with the Web Audio API.
//     Speaking time and pauses come from the signal itself, not from the transcript.
//   - interviewer voice: speechSynthesis

import { useCallback, useEffect, useRef, useState } from "react";
import type { AudioMetrics } from "./api";

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};

function recognitionCtor(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function voiceSupport() {
  return {
    transcript: recognitionCtor() !== null,
    microphone: typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia,
    speech: typeof window !== "undefined" && "speechSynthesis" in window,
  };
}

const FRAME_MS = 50;
const MIN_PAUSE_MS = 250;

export function useRecorder() {
  const [recording, setRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [interim, setInterim] = useState("");
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const rec = useRef<SpeechRecognitionLike | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const timer = useRef<number | null>(null);
  const active = useRef(false);
  const finals = useRef<string[]>([]);
  // audio measurement state
  const m = useRef({ start: 0, frames: 0, noise: [] as number[], threshold: 0.02, speaking: 0, firstSpeech: -1, lastSpeech: -1, silenceRun: 0, hang: 0, pauses: [] as number[] });

  const cleanup = useCallback(() => {
    active.current = false;
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    rec.current?.abort();
    rec.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    void audioCtx.current?.close();
    audioCtx.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const start = useCallback(async () => {
    setError(null);
    setTranscript("");
    setInterim("");
    finals.current = [];
    m.current = { start: performance.now(), frames: 0, noise: [], threshold: 0.02, speaking: 0, firstSpeech: -1, lastSpeech: -1, silenceRun: 0, hang: 0, pauses: [] };
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      setError("Microphone access was blocked. Allow it in the browser's address bar, or type your answer instead.");
      return false;
    }
    const ctx = new AudioContext();
    audioCtx.current = ctx;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream.current).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);

    timer.current = window.setInterval(() => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += (buf[i] ?? 0) * (buf[i] ?? 0);
      const rms = Math.sqrt(sum / buf.length);
      const s = m.current;
      s.frames += 1;
      setLevel(Math.min(1, rms * 12));
      setElapsed((performance.now() - s.start) / 1000);
      if (s.frames <= 8) {
        // first 400 ms: learn the room's noise floor
        s.noise.push(rms);
        s.threshold = Math.max(0.012, (s.noise.reduce((a, b) => a + b, 0) / s.noise.length) * 3);
        return;
      }
      const t = s.frames * FRAME_MS;
      if (rms > s.threshold) {
        if (s.firstSpeech >= 0 && s.silenceRun >= MIN_PAUSE_MS) s.pauses.push(s.silenceRun);
        if (s.firstSpeech < 0) s.firstSpeech = t;
        s.lastSpeech = t;
        s.silenceRun = 0;
        s.hang = 3; // 150 ms hangover so syllable gaps don't count as silence
        s.speaking += FRAME_MS;
      } else if (s.hang > 0) {
        s.hang -= 1;
        s.speaking += FRAME_MS;
      } else if (s.firstSpeech >= 0) {
        s.silenceRun += FRAME_MS;
      }
    }, FRAME_MS);

    const Ctor = recognitionCtor();
    if (Ctor) {
      const r = new Ctor();
      r.continuous = true;
      r.interimResults = true;
      r.lang = "en-US";
      r.onresult = (e) => {
        let live = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const res = e.results[i];
          if (!res) continue;
          if (res.isFinal) finals.current.push(res[0].transcript.trim());
          else live += res[0].transcript;
        }
        setTranscript(finals.current.join(" "));
        setInterim(live);
      };
      r.onerror = (e) => {
        if (e.error === "not-allowed") setError("Speech recognition was blocked. You can still type your answer.");
      };
      // Chrome ends recognition after silence; keep it going while recording.
      r.onend = () => {
        if (active.current) {
          try {
            r.start();
          } catch {
            /* already started */
          }
        }
      };
      rec.current = r;
      try {
        r.start();
      } catch {
        /* ignore double start */
      }
    }
    active.current = true;
    setRecording(true);
    return true;
  }, []);

  const stop = useCallback((): { transcript: string; audio: AudioMetrics } => {
    const s = m.current;
    const span = s.firstSpeech >= 0 ? (s.lastSpeech - s.firstSpeech + FRAME_MS) / 1000 : 0;
    const audio: AudioMetrics = { duration_s: Math.round(span * 10) / 10, speaking_s: Math.round((s.speaking / 1000) * 10) / 10, pauses_ms: s.pauses };
    const text = [finals.current.join(" "), interim].join(" ").replace(/\s+/g, " ").trim();
    cleanup();
    setRecording(false);
    setLevel(0);
    setTranscript(text);
    setInterim("");
    return { transcript: text, audio };
  }, [cleanup, interim]);

  return { recording, transcript, setTranscript, interim, level, elapsed, error, start, stop };
}

export function speak(text: string, onEnd?: () => void) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    onEnd?.();
    return;
  }
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  const voices = window.speechSynthesis.getVoices();
  const voice = voices.find((v) => /en-US/i.test(v.lang) && /natural|aria|jenny|guy|google/i.test(v.name)) ?? voices.find((v) => /^en/i.test(v.lang));
  if (voice) u.voice = voice;
  u.rate = 1.02;
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  window.speechSynthesis.speak(u);
}

export function stopSpeaking() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
}
