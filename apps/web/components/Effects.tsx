"use client";

import { useMemo } from "react";

/** Shards that burst from a point, plus a ring flash. Re-mount (change `key`) to replay. */
export function ImpactBurst({ color = "#FFC857", count = 12, spread = 130, big = false }: { color?: string; count?: number; spread?: number; big?: boolean }) {
  const shards = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => {
        const angle = (i / count) * Math.PI * 2 + (Math.random() - 0.5) * 0.6;
        const dist = spread * (0.55 + Math.random() * 0.6);
        return {
          dx: `${Math.cos(angle) * dist}px`,
          dy: `${Math.sin(angle) * dist}px`,
          rot: `${Math.round((Math.random() - 0.5) * 540)}deg`,
          size: (big ? 16 : 12) + Math.random() * (big ? 16 : 12),
          delay: Math.random() * 60,
        };
      }),
    [count, spread, big],
  );
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden>
      <span
        className="absolute left-1/2 top-1/2 h-40 w-40 animate-flash rounded-full border-4"
        style={{ borderColor: color }}
      />
      {shards.map((s, i) => (
        <span
          key={i}
          className="absolute left-1/2 top-1/2 animate-burst"
          style={
            {
              width: s.size,
              height: s.size * 0.45,
              background: color,
              boxShadow: `0 0 8px ${color}`,
              clipPath: "polygon(0 50%, 30% 0, 100% 50%, 30% 100%)",
              animationDelay: `${s.delay}ms`,
              "--dx": s.dx,
              "--dy": s.dy,
              "--rot": s.rot,
            } as React.CSSProperties
          }
        />
      ))}
    </div>
  );
}

/** Red edge glow when the boss lands a hit on you. */
export function HurtVignette() {
  return (
    <div
      className="pointer-events-none fixed inset-0 z-40 animate-vignette"
      style={{ background: "radial-gradient(ellipse at center, transparent 55%, rgba(255,61,102,0.38) 100%)" }}
      aria-hidden
    />
  );
}
