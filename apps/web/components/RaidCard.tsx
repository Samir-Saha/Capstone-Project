"use client";

import { Hourglass } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { BossArt } from "@/components/BossArt";
import { ErrorNote } from "@/components/ui";
import { api, type RaidPreview } from "@/lib/api";

export function RaidCard({ raid }: { raid: RaidPreview }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const done = raid.status === "completed";
  const active = raid.status === "active";

  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      const f = active && raid.session_id ? { id: raid.session_id } : await api.startRaid();
      router.push(`/exam/${f.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <section className="panel relative overflow-hidden p-6" aria-labelledby="raid-title">
      <div className="flex items-start gap-4">
        <BossArt courseId="daily-raid" name="The Fading" className="-ml-2 -mt-2 h-24 w-24 shrink-0" track />
        <div className="min-w-0 flex-1">
          <h2 id="raid-title" className="h-display flex items-center gap-2 text-xl">
            <Hourglass size={18} className="text-xp" aria-hidden /> Daily Raid
          </h2>
          <p className="mt-1 text-sm text-muted">
            {raid.topics.length === 0
              ? "Unlocks after your first boss fight. It targets whatever you're starting to forget."
              : done
                ? raid.outcome === "victory"
                  ? "Cleared today. A new raid opens tomorrow."
                  : "Done for today. Those topics come back tomorrow."
                : `${raid.length} questions on what's fading, ${raid.hearts} hearts, +${raid.xp} XP if you clear it.`}
          </p>
        </div>
      </div>
      {raid.topics.length > 0 && !done && (
        <ul className="mt-4 space-y-1.5 text-sm">
          {raid.topics.map((t) => (
            <li key={t.id} className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate">
                {t.name} <span className="text-muted">{t.course}</span>
              </span>
              <span className="shrink-0 tabular-nums">
                {Math.round(t.mastery * 100)}%
                {(t.fading ?? 0) >= 0.005 && <span className="ml-1.5 text-hp">−{Math.round((t.fading ?? 0) * 100)} faded</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      {raid.topics.length > 0 && !done && (
        <button type="button" className="btn mt-4 w-full bg-xp text-ink hover:bg-[#ffd47a]" onClick={go} disabled={busy}>
          {busy ? "Opening" : active ? "Resume today's raid" : "Start today's raid"}
        </button>
      )}
      {error && (
        <div className="mt-3">
          <ErrorNote message={error} />
        </div>
      )}
    </section>
  );
}
