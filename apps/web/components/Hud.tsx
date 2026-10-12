"use client";

import { Heart } from "lucide-react";
import type { Topic } from "@/lib/api";
import { useEffect, useRef, useState } from "react";
import { useTween } from "@/lib/motion";

/**
 * Boss HP, built from one segment per topic. Each segment is as wide as its share of
 * the course and filled by (1 - mastery), so the bar's total fill is exactly the HP:
 * 100 x (1 - average mastery). The long segments are the topics to work on.
 */
export function SegmentedHp({
  topics,
  hp,
  victoryHp,
  activeTopicId,
  compact = false,
}: {
  topics: Topic[];
  hp: number;
  victoryHp?: number | null;
  activeTopicId?: string | null;
  compact?: boolean;
}) {
  const n = Math.max(topics.length, 1);
  const shownHp = useTween(hp);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="font-display text-sm font-semibold text-hp">
          Boss HP
          {victoryHp != null && <span className="ml-2 font-sans text-xs font-normal text-muted">win at {victoryHp} or less</span>}
        </span>
        <span className="font-display text-2xl font-bold tabular-nums text-text">
          <span aria-hidden>{shownHp}</span>
          <span className="sr-only">{hp}</span>
          <span className="text-sm font-medium text-muted"> / 100</span>
        </span>
      </div>
      <div className={`relative flex ${compact ? "h-3" : "h-5"} w-full gap-[3px] rounded-md bg-ink/80 p-[3px] ring-1 ring-line`}>
        {topics.map((t) => {
          const fill = Math.max(0, Math.min(1, 1 - t.mastery));
          const active = t.id === activeTopicId;
          return (
            <div
              key={t.id}
              className={`relative h-full overflow-hidden rounded-[3px] bg-raised ${active ? "ring-2 ring-xp ring-offset-1 ring-offset-ink" : ""}`}
              style={{ width: `${100 / n}%` }}
              title={`${t.name}: ${Math.round(t.mastery * 100)}% mastery`}
            >
              {/* damage trail: lags behind the real bar so you can see where the hit landed */}
              <div
                className="absolute inset-y-0 left-0 bg-[#FFE3A3] transition-[width] delay-[450ms] duration-[650ms] ease-in"
                style={{ width: `${fill * 100}%` }}
              />
              <div
                className="absolute inset-y-0 left-0 bg-gradient-to-r from-[#FF3D66] to-hp transition-[width] duration-200 ease-out"
                style={{ width: `${fill * 100}%` }}
              />
            </div>
          );
        })}
      </div>
      {!compact && (
        <div className="mt-1.5 flex w-full gap-[3px] px-[3px]">
          {topics.map((t) => (
            <div
              key={t.id}
              className={`line-clamp-2 text-[11px] leading-tight ${t.id === activeTopicId ? "font-semibold text-xp" : "text-muted"}`}
              style={{ width: `${100 / n}%` }}
            >
              {t.name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Hearts({ hearts, max }: { hearts: number; max: number }) {
  // Keep the breaking heart on screen for its whole animation, even through re-renders.
  const prev = useRef(hearts);
  const [lost, setLost] = useState<{ from: number; to: number } | null>(null);
  useEffect(() => {
    if (hearts < prev.current) {
      setLost({ from: hearts, to: prev.current });
      const t = setTimeout(() => setLost(null), 700);
      prev.current = hearts;
      return () => clearTimeout(t);
    }
    prev.current = hearts;
  }, [hearts]);
  return (
    <div className="flex items-center gap-1" role="img" aria-label={`${hearts} of ${max} hearts left`}>
      {Array.from({ length: max }, (_, i) => (
        <span key={i} className="relative inline-flex">
          <Heart
            size={22}
            className={`transition-all duration-300 ${i < hearts ? "fill-hp text-hp drop-shadow-[0_0_6px_rgba(255,92,122,0.5)]" : "scale-90 fill-transparent text-line"}`}
            aria-hidden
          />
          {lost && i >= lost.from && i < lost.to && (
            <Heart key={`break-${hearts}`} size={22} className="absolute inset-0 animate-heartbreak fill-hp text-hp" aria-hidden />
          )}
        </span>
      ))}
    </div>
  );
}

export function MasteryBar({ value, provisional, tone = "violet" }: { value: number; provisional?: boolean; tone?: "violet" | "cyan" }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink ring-1 ring-line">
        <div
          className={`h-full rounded-full transition-[width] duration-700 ${tone === "violet" ? "bg-violet" : "bg-cyan"} ${provisional ? "opacity-50" : ""}`}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
      <span className="w-10 text-right font-display text-xs tabular-nums text-muted">{Math.round(value * 100)}%</span>
    </div>
  );
}

export function DifficultyPips({ level, max = 3 }: { level: number; max?: number }) {
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`Difficulty ${level} of ${max}`}>
      {Array.from({ length: max }, (_, i) => (
        <span key={i} className={`h-2.5 w-1.5 rounded-sm ${i < level ? "bg-xp" : "bg-line"}`} />
      ))}
    </span>
  );
}
