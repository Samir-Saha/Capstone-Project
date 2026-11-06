"use client";

import { Code2, Flame, Home, LineChart, Mic, Settings, Swords, Users, Volume2, VolumeX } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AchievementIcon } from "@/components/AchievementIcon";
import { api, type Player } from "@/lib/api";
import { play, setSoundEnabled, soundEnabled } from "@/lib/sound";

const NAV = [
  { href: "/", label: "Hub", icon: Home, match: (p: string) => p === "/" },
  { href: "/exam", label: "Boss fights", icon: Swords, match: (p: string) => p.startsWith("/exam") },
  { href: "/party", label: "Party", icon: Users, match: (p: string) => p.startsWith("/party") },
  { href: "/arena", label: "Arena", icon: Code2, match: (p: string) => p.startsWith("/arena") },
  { href: "/interview", label: "Gauntlet", icon: Mic, match: (p: string) => p.startsWith("/interview") },
  { href: "/progress", label: "Progress", icon: LineChart, match: (p: string) => p.startsWith("/progress") },
  { href: "/settings", label: "Profile", icon: Settings, match: (p: string) => p.startsWith("/settings") },
];

function Wordmark() {
  return (
    <Link href="/" className="group flex items-center gap-2.5 px-2" aria-label="Reps hub">
      <svg viewBox="0 0 32 32" className="h-8 w-8 transition-transform duration-300 group-hover:-rotate-6 group-hover:scale-110" aria-hidden>
        <rect x="2" y="2" width="28" height="28" rx="8" fill="#6D4AFF" />
        <path d="M9 23 V9 h7 a5 5 0 0 1 0 10 h-7 M16 19 l6 4" stroke="#FFFFFF" strokeWidth="3.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="font-display text-xl font-bold tracking-tight">Reps</span>
    </Link>
  );
}

const MAX_TOASTS = 2;

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [player, setPlayer] = useState<Player | null>(null);
  const [offline, setOffline] = useState(false);
  const [sound, setSound] = useState(false);
  const [gain, setGain] = useState<{ id: number; xp: number } | null>(null);
  const [levelUp, setLevelUp] = useState<number | null>(null);
  const [toasts, setToasts] = useState<Player["new_achievements"]>([]);
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
      if (p.new_achievements.length) {
        setToasts((t) => [...t, ...p.new_achievements.filter((a) => !t.some((x) => x.key === a.key))]);
        play("accepted");
        void api.markSeen(p.new_achievements.map((a) => a.key)).catch(() => undefined);
        const keys = p.new_achievements.map((a) => a.key);
        setTimeout(() => setToasts((t) => t.filter((x) => !keys.includes(x.key))), 6000);
      }
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
    const onSound = (e: Event) => setSound(Boolean((e as CustomEvent<boolean>).detail));
    window.addEventListener("reps:sound", onSound);
    return () => {
      window.removeEventListener("reps:progress", onProgress);
      window.removeEventListener("reps:sound", onSound);
    };
  }, [refresh]);

  const pct = player ? Math.round((player.xp_into_level / player.xp_for_next) * 100) : 0;

  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 btn-primary">
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-screen w-[212px] shrink-0 flex-col border-r border-line bg-surface/80 py-5 backdrop-blur-md md:flex">
        <Wordmark />
        <nav className="mt-8 flex flex-col gap-1 px-3" aria-label="Main">
          {NAV.map(({ href, label, icon: Icon, match }) => {
            const active = match(pathname);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-chip px-3 py-2.5 font-display text-[15px] font-semibold transition-all ${
                  active ? "bg-violet/10 text-violet-deep shadow-[inset_3px_0_0_rgb(109,74,255)]" : "text-muted hover:translate-x-0.5 hover:bg-raised hover:text-text"
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
        <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-line bg-surface/80 px-4 backdrop-blur-md md:px-8">
          <div className="md:hidden">
            <Wordmark />
          </div>
          <div className="ml-auto flex items-center gap-2 sm:gap-5">
            {player && (
              <>
                <div className="flex items-center gap-1.5" title={`Best streak: ${player.best_streak} days`}>
                  <Flame size={18} className={player.streak > 0 ? "fill-xp/30 text-xp" : "text-muted"} aria-hidden />
                  <span className="whitespace-nowrap font-display text-sm font-semibold tabular-nums">
                    {player.streak} <span className="hidden font-normal text-muted sm:inline">day streak</span>
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
                      <div className="h-full rounded-full bg-gradient-to-r from-sun to-[#FF9F1C] transition-[width] duration-700" style={{ width: `${pct}%` }} />
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
            <Link
              href="/progress"
              className={`flex h-11 w-11 items-center justify-center rounded-chip md:hidden ${pathname.startsWith("/progress") ? "text-violet-soft" : "text-muted"} hover:bg-raised hover:text-text`}
              aria-label="Progress"
            >
              <LineChart size={20} aria-hidden />
            </Link>
            <Link
              href="/settings"
              className={`flex h-11 w-11 items-center justify-center rounded-chip md:hidden ${pathname.startsWith("/settings") ? "text-violet-soft" : "text-muted"} hover:bg-raised hover:text-text`}
              aria-label="Profile and settings"
            >
              <Settings size={20} aria-hidden />
            </Link>
            <button
              type="button"
              className="flex h-11 w-11 items-center justify-center rounded-chip text-muted hover:bg-raised hover:text-text"
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
          <div key={pathname} className="page-in">
            {children}
          </div>
        </main>

        <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface/95 backdrop-blur md:hidden" aria-label="Main">
          {NAV.filter((n) => n.href !== "/progress" && n.href !== "/settings").map(({ href, label, icon: Icon, match }) => (
            <Link
              key={href}
              href={href}
              aria-current={match(pathname) ? "page" : undefined}
              className={`flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 py-2 text-xs font-medium transition-colors ${match(pathname) ? "text-violet-soft" : "text-muted active:text-text"}`}
            >
              <Icon size={20} aria-hidden />
              {label}
            </Link>
          ))}
        </nav>
      </div>

      <div className="pointer-events-none fixed bottom-20 right-4 z-50 flex w-[320px] flex-col gap-3 md:bottom-6" role="status" aria-live="polite">
        {toasts.slice(0, MAX_TOASTS).map((a) => (
          <div key={a.key} className="pointer-events-auto flex animate-pop items-start gap-3 rounded-panel border border-xp/50 bg-surface/95 p-4 shadow-[0_10px_40px_-10px_rgba(224,154,0,0.45)]">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-xp/20 text-xp ring-1 ring-xp/40">
              <AchievementIcon name={a.icon} />
            </span>
            <div className="min-w-0">
              <div className="text-xs text-xp">Achievement unlocked, +20 XP</div>
              <div className="font-display font-semibold">{a.name}</div>
              <div className="text-sm text-muted">{a.text}</div>
            </div>
          </div>
        ))}
        {toasts.length > MAX_TOASTS && (
          <Link
            href="/progress"
            className="pointer-events-auto animate-pop rounded-panel border border-xp/50 bg-surface/95 px-4 py-3 text-sm shadow-[0_10px_40px_-10px_rgba(224,154,0,0.45)] hover:bg-raised"
          >
            <span className="font-display font-semibold text-xp">+{toasts.length - MAX_TOASTS} more achievements.</span>{" "}
            <span className="text-muted">See them on Progress.</span>
          </Link>
        )}
      </div>

      {levelUp !== null && (
        <div className="pointer-events-none fixed inset-x-0 top-20 z-50 flex justify-center" role="status">
          <div className="flex animate-pop items-center gap-4 rounded-panel border border-xp/60 bg-surface/95 px-6 py-3 shadow-[0_0_60px_-10px_rgba(224,154,0,0.5)]">
            <div className="font-display text-sm font-semibold text-xp">Level up</div>
            <div className="font-display text-4xl font-bold">{levelUp}</div>
          </div>
        </div>
      )}
    </div>
  );
}
