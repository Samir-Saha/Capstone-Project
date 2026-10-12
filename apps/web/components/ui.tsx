"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { useCountUp } from "@/lib/motion";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-muted" role="status">
      <Loader2 size={18} className="animate-spin" aria-hidden />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-chip border border-hp/40 bg-hp/10 px-4 py-3 text-sm" role="alert">
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-hp" aria-hidden />
      <div className="flex-1">{message}</div>
      {onRetry && (
        <button type="button" className="font-display font-semibold text-text underline-offset-2 hover:underline" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function CountStat({ value, of, label, tone = "text" }: { value: number; of?: number; label: string; tone?: "text" | "xp" | "heal" | "hp" | "cyan" }) {
  const shown = useCountUp(value);
  return <Stat value={of !== undefined ? `${shown}/${of}` : shown} label={label} tone={tone} />;
}

export function Stat({ value, label, tone = "text" }: { value: React.ReactNode; label: string; tone?: "text" | "xp" | "heal" | "hp" | "cyan" }) {
  const color = { text: "text-text", xp: "text-xp", heal: "text-heal", hp: "text-hp", cyan: "text-cyan" }[tone];
  return (
    <div>
      <div className={`font-display text-3xl font-bold tabular-nums ${color}`}>{value}</div>
      <div className="text-sm text-muted">{label}</div>
    </div>
  );
}

export const XP_REASON: Record<string, string> = {
  exam_correct: "Verified correct answer",
  boss_defeated: "Boss defeated",
  exam_session_finished: "Fight finished",
  coding_accepted_easy: "Solved an easy problem",
  coding_accepted_medium: "Solved a medium problem",
  coding_accepted_hard: "Solved a hard problem",
  interview_answer: "Interview answer",
  interview_finished: "Interview finished",
};

export function timeAgo(iso: string) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}
