"use client";

import { Code2, Flame, Home, Mic, Swords, Volume2, VolumeX } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Player } from "@/lib/api";
import { play, setSoundEnabled, soundEnabled } from "@/lib/sound";

const NAV = [
  { href: "/", label: "Hub", icon: Home, match: (p: string) => p === "/" },
  { href: "/exam", label: "Boss fights", icon: Swords, match: (p: string) => p.startsWith("/exam") },
  { href: "/arena", label: "Arena", icon: Code2, match: (p: string) => p.startsWith("/arena") },
  { href: "/interview", label: "Gauntlet", icon: Mic, match: (p: string) => p.startsWith("/interview") },
];

function Wordmark() {
  return (
    <Link href="/" className="group flex items-center gap-2.5 px-2" aria-label="Reps hub">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect x="2" y="2" width="28" height="28" rx="8" fill="#8B6CFF" />
        <path d="M9 23 V9 h7 a5 5 0 0 1 0 10 h-7 M16 19 l6 4" stroke="#0E1020" strokeWidth="3.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="font-display text-xl font-bold tracking-tight">Reps</span>
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [player, setPlayer] = useState<Player | null>(null);
  const [offline, setOffline] = useState(false);
  const [sound, setSound] = useState(false);
  const [gain, setGain] = useState<{ id: number; xp: number } | null>(null);
  const [levelUp, setLevelUp] = useState<number | null>(null);
  const lastLevel = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const p = await api.player();
      setPlayer(p);
      setOffline(false);
      if (lastLevel.current !== null && p.level > lastLevel.current) {
        setLevelUp(p.level);
        play("levelup");
        setTimeout(() => setLevelUp(null), 3200);
      }
      lastLevel.current = p.level;
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    setSound(soundEnabled());
    const onProgress = (e: Event) => {
      const xp = (e as CustomEvent<{ xp: number }>).detail?.xp ?? 0;
      if (xp > 0) setGain({ id: Date.now(), xp });
      void refresh();
    };
    window.addEventListener("reps:progress", onProgress);
    return () => window.removeEventListener("reps:progress", onProgress);
  }, [refresh]);

  const pct = player ? Math.round((player.xp_into_level / player.xp_for_next) * 100) : 0;

  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 btn-primary">
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-screen w-[212px] shrink-0 flex-col border-r border-line bg-surface/70 py-5 backdrop-blur md:flex">
        <Wordmark />
        <nav className="mt-8 flex flex-col gap-1 px-3" aria-label="Main">
          {NAV.map(({ href, label, icon: Icon, match }) => {
            const active = match(pathname);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-chip px-3 py-2.5 font-display text-[15px] font-semibold transition-colors ${
                  active ? "bg-violet/15 text-text shadow-[inset_3px_0_0_#8B6CFF]" : "text-muted hover:bg-raised hover:text-text"
                }`}
              >
                <Icon size={18} aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto px-5 text-xs leading-relaxed text-muted">
          Local mode. Progress is saved on this computer.
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-line bg-ink/85 px-4 backdrop-blur md:px-8">
          <div className="md:hidden">
            <Wordmark />
          </div>
          <div className="ml-auto flex items-center gap-5">
            {player && (
              <>
                <div className="flex items-center gap-1.5" title={`Best streak: ${player.best_streak} days`}>
                  <Flame size={18} className={player.streak > 0 ? "fill-xp/30 text-xp" : "text-muted"} aria-hidden />
                  <span className="font-display text-sm font-semibold tabular-nums">
                    {player.streak} <span className="font-normal text-muted">day streak</span>
                  </span>
                </div>
                <div className="relative flex items-center gap-3" title={`${player.xp} XP total`}>
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet/20 font-display text-base font-bold text-violet-soft ring-1 ring-violet/50">
                    {player.level}
                  </div>
                  <div className="hidden w-40 sm:block">
                    <div className="flex justify-between text-[11px] text-muted">
                      <span>Level {player.level}</span>
                      <span className="tabular-nums">
                        {player.xp_into_level}/{player.xp_for_next} XP
                      </span>
                    </div>
                    <div key={gain?.id ?? 0} className={`mt-1 h-1.5 overflow-hidden rounded-full bg-raised ${gain ? "animate-glow" : ""}`}>
                      <div className="h-full rounded-full bg-xp transition-[width] duration-700" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                  {gain && (
                    <span key={gain.id} className="pointer-events-none absolute right-0 top-full mt-2 animate-rise font-display text-sm font-bold text-xp">
                      +{gain.xp} XP
                    </span>
                  )}
                </div>
              </>
            )}
            <button
              type="button"
              className="rounded-chip p-2 text-muted hover:bg-raised hover:text-text"
              onClick={() => {
                setSoundEnabled(!sound);
                setSound(!sound);
                if (!sound) setTimeout(() => play("tick"), 10);
              }}
              aria-pressed={sound}
              aria-label={sound ? "Turn sound off" : "Turn sound on"}
              title={sound ? "Sound on" : "Sound off"}
            >
              {sound ? <Volume2 size={18} /> : <VolumeX size={18} />}
            </button>
          </div>
        </header>

        {offline && (
          <div className="border-b border-hp/40 bg-hp/10 px-8 py-2.5 text-sm text-text" role="alert">
            Can't reach the Reps API. Start it with <code className="font-mono text-xp">start-reps.bat</code> (or see the README), then refresh.
          </div>
        )}

        <main id="main" className="mx-auto w-full max-w-[1280px] flex-1 px-4 pb-24 pt-8 md:px-8">
          {children}
        </main>

        <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface/95 backdrop-blur md:hidden" aria-label="Main">
          {NAV.map(({ href, label, icon: Icon, match }) => (
            <Link
              key={href}
              href={href}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${match(pathname) ? "text-violet-soft" : "text-muted"}`}
            >
              <Icon size={20} aria-hidden />
              {label}
            </Link>
          ))}
        </nav>
      </div>

      {levelUp !== null && (
        <div className="pointer-events-none fixed inset-x-0 top-20 z-50 flex justify-center" role="status">
          <div className="flex animate-pop items-center gap-4 rounded-panel border border-xp/60 bg-surface/95 px-6 py-3 shadow-[0_0_60px_-10px_rgba(255,200,87,0.6)]">
            <div className="font-display text-sm font-semibold text-xp">Level up</div>
            <div className="font-display text-4xl font-bold">{levelUp}</div>
          </div>
        </div>
      )}
    </div>
  );
}
