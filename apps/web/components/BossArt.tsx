"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "@/lib/motion";

// Original boss illustrations, drawn in SVG. One per built-in course, plus a
// generated variant for uploaded courses (colors seeded from the boss name).

export type BossState = "idle" | "hit" | "attack" | "windup" | "defeated" | "victor";
type Props = { courseId: string; name: string; state?: BossState; className?: string; track?: boolean };
type Look = { x: number; y: number };

function hue(name: string) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

function Vexis({ look }: { look: Look }) {
  // A crystalline eye wrapped in integral-sign tendrils.
  return (
    <svg viewBox="0 0 320 320" className="h-full w-full" aria-hidden>
      <defs>
        <radialGradient id="vx-core" cx="50%" cy="45%" r="55%">
          <stop offset="0%" stopColor="#F4EEFF" />
          <stop offset="35%" stopColor="#B9A8FF" />
          <stop offset="100%" stopColor="#3A1F9E" />
        </radialGradient>
        <linearGradient id="vx-shard" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#8B6CFF" />
          <stop offset="100%" stopColor="#2B1A73" />
        </linearGradient>
        <filter id="vx-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="8" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <ellipse cx="160" cy="292" rx="88" ry="12" fill="#000" opacity="0.35" />
      {/* tendrils shaped like integral signs */}
      {[-1, 1].map((s) => (
        <g key={s} stroke="#8B6CFF" strokeWidth="9" fill="none" strokeLinecap="round" opacity="0.9">
          <path d={`M ${160 + s * 70} 70 C ${160 + s * 120} 60, ${160 + s * 120} 130, ${160 + s * 95} 160 S ${160 + s * 70} 250, ${160 + s * 120} 255`} />
          <path
            d={`M ${160 + s * 52} 98 C ${160 + s * 90} 100, ${160 + s * 92} 150, ${160 + s * 78} 175 S ${160 + s * 64} 220, ${160 + s * 92} 232`}
            stroke="#3FD8E6"
            strokeWidth="4"
            opacity="0.7"
          />
        </g>
      ))}
      {/* shard crown */}
      <g fill="url(#vx-shard)" stroke="#B9A8FF" strokeWidth="1.5">
        <path d="M160 18 L178 78 L142 78 Z" />
        <path d="M112 40 L140 88 L108 96 Z" />
        <path d="M208 40 L212 96 L180 88 Z" />
      </g>
      {/* body */}
      <path d="M160 70 L236 150 L160 262 L84 150 Z" fill="url(#vx-shard)" stroke="#B9A8FF" strokeWidth="2" />
      <path d="M160 70 L160 262 M84 150 L236 150" stroke="#B9A8FF" strokeWidth="1" opacity="0.35" />
      {/* eye */}
      <g filter="url(#vx-glow)">
        <ellipse cx="160" cy="150" rx="44" ry="30" fill="#0E1020" stroke="#B9A8FF" strokeWidth="2" />
        <g style={{ transform: `translate(${look.x * 14}px, ${look.y * 7}px)`, transition: "transform 120ms ease-out" }}>
          <circle cx="160" cy="150" r="22" fill="url(#vx-core)" />
          <ellipse cx="160" cy="150" rx="5" ry="16" fill="#0E1020" />
          <circle cx="152" cy="142" r="4" fill="#fff" opacity="0.9" />
        </g>
      </g>
    </svg>
  );
}

function Kinetor({ look }: { look: Look }) {
  // A rolling armored sphere with motion trails and vector arms.
  return (
    <svg viewBox="0 0 320 320" className="h-full w-full" aria-hidden>
      <defs>
        <radialGradient id="kt-body" cx="40%" cy="35%" r="70%">
          <stop offset="0%" stopColor="#9FF3FA" />
          <stop offset="40%" stopColor="#1A9FB0" />
          <stop offset="100%" stopColor="#0B3440" />
        </radialGradient>
        <filter id="kt-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <ellipse cx="160" cy="292" rx="96" ry="12" fill="#000" opacity="0.35" />
      {/* motion trails */}
      <g stroke="#3FD8E6" strokeLinecap="round" opacity="0.6">
        <path d="M18 130 H70" strokeWidth="6" />
        <path d="M30 165 H62" strokeWidth="4" />
        <path d="M10 200 H72" strokeWidth="6" />
      </g>
      {/* vector arms */}
      <g stroke="#FFC857" strokeWidth="7" strokeLinecap="round" fill="#FFC857">
        <path d="M232 120 L292 70" />
        <path d="M292 70 l-24 4 l14 18 Z" strokeWidth="2" />
        <path d="M238 210 L296 236" />
        <path d="M296 236 l-14 -20 l-8 22 Z" strokeWidth="2" />
      </g>
      <circle cx="160" cy="166" r="96" fill="url(#kt-body)" stroke="#9FF3FA" strokeWidth="2" />
      {/* armor plates */}
      <g fill="none" stroke="#0B3440" strokeWidth="5" opacity="0.65">
        <path d="M74 140 Q160 110 246 140" />
        <path d="M70 196 Q160 226 250 196" />
        <path d="M160 70 Q130 166 160 262" />
      </g>
      {/* visor */}
      <g filter="url(#kt-glow)">
        <rect x="110" y="140" width="100" height="34" rx="17" fill="#0E1020" stroke="#9FF3FA" strokeWidth="2" />
        <g style={{ transform: `translate(${look.x * 9}px, ${look.y * 4}px)`, transition: "transform 120ms ease-out" }}>
          <rect x="124" y="150" width="34" height="14" rx="7" fill="#FFC857" />
          <rect x="166" y="150" width="34" height="14" rx="7" fill="#FFC857" />
        </g>
      </g>
    </svg>
  );
}

function Generated({ name, look }: { name: string; look: Look }) {
  const h = hue(name);
  const a = `hsl(${h} 85% 66%)`;
  const b = `hsl(${(h + 40) % 360} 70% 30%)`;
  const id = `g${h}`;
  return (
    <svg viewBox="0 0 320 320" className="h-full w-full" aria-hidden>
      <defs>
        <radialGradient id={id} cx="45%" cy="40%" r="65%">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.9" />
          <stop offset="30%" stopColor={a} />
          <stop offset="100%" stopColor={b} />
        </radialGradient>
      </defs>
      <ellipse cx="160" cy="292" rx="88" ry="12" fill="#000" opacity="0.35" />
      {[0, 60, 120, 180, 240, 300].map((r) => (
        <path key={r} d="M160 160 L160 40 L186 120 Z" fill={a} opacity="0.55" transform={`rotate(${r} 160 160)`} />
      ))}
      <circle cx="160" cy="160" r="78" fill={`url(#${id})`} stroke={a} strokeWidth="2" />
      <ellipse cx="160" cy="158" rx="34" ry="20" fill="#0E1020" />
      <circle cx="160" cy="158" r="11" fill={a} style={{ transform: `translate(${look.x * 16}px, ${look.y * 7}px)`, transition: "transform 120ms ease-out" }} />
    </svg>
  );
}

const ANIM: Record<BossState, string> = {
  idle: "animate-float",
  hit: "animate-hit",
  attack: "animate-lunge",
  windup: "animate-windup",
  defeated: "animate-shatter",
  victor: "animate-loom",
};

export function BossArt({ courseId, name, state = "idle", className = "", track = false }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const [look, setLook] = useState<Look>({ x: 0, y: 0 });

  // The boss's eye follows your cursor during a fight.
  useEffect(() => {
    if (!track || reduced) return;
    let raf = 0;
    const onMove = (e: PointerEvent) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const box = ref.current?.getBoundingClientRect();
        if (!box) return;
        const dx = (e.clientX - (box.left + box.width / 2)) / (window.innerWidth / 2);
        const dy = (e.clientY - (box.top + box.height / 2)) / (window.innerHeight / 2);
        setLook({ x: Math.max(-1, Math.min(1, dx)), y: Math.max(-1, Math.min(1, dy)) });
      });
    };
    window.addEventListener("pointermove", onMove);
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(raf);
    };
  }, [track, reduced]);

  const still = state === "defeated" ? { x: 0, y: 0.6 } : look;
  return (
    <div ref={ref} className={`relative ${className}`} role="img" aria-label={`${name}, the boss`}>
      <div key={state} className={ANIM[state]}>
        {courseId === "calc-1" ? <Vexis look={still} /> : courseId === "phys-kinematics" ? <Kinetor look={still} /> : <Generated name={name} look={still} />}
      </div>
    </div>
  );
}
