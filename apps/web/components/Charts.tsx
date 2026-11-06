"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";

// Categorical slots, validated against the dark card surface (#171936) for lightness,
// chroma, colorblind separation and 3:1 contrast. Assigned by topic order, never cycled.
export const SERIES = ["#3B82F6", "#EA580C", "#0D9488", "#C026D3", "#A16207", "#8B5CF6"];

const GRID = "#2C2F59";
const MUTED = "#A1A1C2";
const SURFACE = "#171936";

/** Width of a container in CSS pixels, so the SVG draws at 1:1 and text stays 11px. */
function useWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(Math.max(240, Math.round(el.getBoundingClientRect().width)));
    const ro = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(240, Math.round(entry.contentRect.width)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** 0 and up to three more ticks on a 1/2/5 step, so labels read 0, 50, 100 rather than 0, 243, 485. */
function niceTicks(max: number): number[] {
  const raw = Math.max(max, 1) / 3;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag) as number;
  const top = Math.ceil(Math.max(max, 1) / step) * step;
  const ticks = [];
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(v);
  return ticks;
}

type Topic = { id: string; name: string };
type Event = { i: number; topic_id: string; before: number; after: number; correct: boolean };

/** Mastery of each topic after every graded answer in a course (step lines). */
export function MasteryChart({ topics, events }: { topics: Topic[]; events: Event[] }) {
  const [box, W] = useWidth<HTMLDivElement>(720);
  const H = W < 520 ? 220 : 280;
  const pad = { l: 40, r: 12, t: 12, b: 26 };
  const n = events.length;
  const x = (i: number) => pad.l + (i / Math.max(n, 1)) * (W - pad.l - pad.r);
  const y = (p: number) => pad.t + (1 - p) * (H - pad.t - pad.b);

  // Value of every topic at each step 0..n (step 0 = before the first answer).
  // A topic has no value until its first answer, so its line starts there.
  const table = useMemo(() => {
    const rows: Record<string, number>[] = [{}];
    for (const e of events) rows.push({ ...rows[rows.length - 1]!, [e.topic_id]: e.after });
    return rows;
  }, [events]);
  const firstAt = useMemo(() => {
    const m: Record<string, Event> = {};
    for (const e of events) m[e.topic_id] ??= e;
    return m;
  }, [events]);

  const [hover, setHover] = useState<number | null>(null);
  const onMove = (ev: React.PointerEvent<SVGSVGElement>) => {
    const r = ev.currentTarget.getBoundingClientRect();
    const i = Math.round(((ev.clientX - r.left - pad.l) / (W - pad.l - pad.r)) * n);
    setHover(Math.max(1, Math.min(n, i)));
  };

  const color = (id: string) => SERIES[topics.findIndex((t) => t.id === id) % SERIES.length]!;
  const touched = topics.filter((t) => firstAt[t.id]);
  const hovered = hover === null ? null : events[hover - 1];
  return (
    <div>
      <ul className="mb-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm" aria-label="Legend">
        {topics.map((t) => (
          <li key={t.id} className={`flex items-center gap-2 ${firstAt[t.id] ? "" : "text-muted"}`}>
            <span className="h-[3px] w-4 rounded-full" style={{ background: color(t.id), opacity: firstAt[t.id] ? 1 : 0.4 }} aria-hidden />
            {t.name}
            {!firstAt[t.id] && <span className="sr-only">(no answers yet)</span>}
          </li>
        ))}
      </ul>
      <div ref={box} className="relative">
        <svg
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          className="block touch-none select-none"
          role="img"
          aria-label={`Mastery by topic over ${n} answers`}
          onPointerMove={onMove}
          onPointerDown={onMove}
          onPointerLeave={() => setHover(null)}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((g) => (
            <g key={g}>
              <line x1={pad.l} x2={W - pad.r} y1={y(g)} y2={y(g)} stroke={GRID} strokeWidth="1" />
              <text x={pad.l - 8} y={y(g) + 4} textAnchor="end" fontSize="11" fill={MUTED}>
                {g * 100}%
              </text>
            </g>
          ))}
          <text x={W - pad.r} y={H - 6} textAnchor="end" fontSize="11" fill={MUTED}>
            answer {n}
          </text>
          {touched.map((t) => {
            const first = firstAt[t.id]!;
            let d = `M ${x(first.i - 1)} ${y(first.before)} V ${y(first.after)}`;
            for (let i = first.i + 1; i <= n; i++) d += ` H ${x(i)} V ${y(table[i]![t.id]!)}`;
            return <path key={t.id} d={d} fill="none" stroke={color(t.id)} strokeWidth="2" strokeLinejoin="round" />;
          })}
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} stroke={MUTED} strokeDasharray="3 3" />}
          {events.map((e) => (
            <circle
              key={e.i}
              cx={x(e.i)}
              cy={y(e.after)}
              r={e.i === hover ? 6 : 4}
              fill={e.correct ? color(e.topic_id) : SURFACE}
              stroke={e.correct ? SURFACE : color(e.topic_id)}
              strokeWidth="2"
            />
          ))}
        </svg>
        {hover !== null && hovered && (
          <div
            className="pointer-events-none absolute top-2 z-10 w-[220px] rounded-chip border border-line bg-surface/95 shadow-lift p-3 text-xs shadow-lg"
            style={x(hover) > W / 2 ? { right: W - x(hover) + 12 } : { left: x(hover) + 12 }}
          >
            <div className="font-semibold">Answer {hover}</div>
            <div className="text-muted">
              {topics.find((t) => t.id === hovered.topic_id)?.name}, {hovered.correct ? "correct" : "missed"}
            </div>
            <div className="mb-2 tabular-nums">
              {Math.round(hovered.before * 100)}% → {Math.round(hovered.after * 100)}%
            </div>
            {touched
              .filter((t) => table[hover]![t.id] !== undefined)
              .map((t) => ({ t, v: table[hover]![t.id]! }))
              .sort((a, b) => b.v - a.v)
              .map(({ t, v }) => (
                <div key={t.id} className="flex items-center justify-between gap-4">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ background: color(t.id) }} />
                    {t.name}
                  </span>
                  <span className="tabular-nums">{Math.round(v * 100)}%</span>
                </div>
              ))}
          </div>
        )}
      </div>
      <p className="mt-2 text-xs text-muted">Filled dots are correct answers, hollow dots are misses. Values are mastery when answered, before any fading since.</p>
    </div>
  );
}

/** One measure across days, with a hover tooltip per bar. */
export function DailyBars({ data, color = "#FBBF24", unit = "XP" }: { data: { day: string; xp: number }[]; color?: string; unit?: string }) {
  const [box, W] = useWidth<HTMLDivElement>(560);
  const H = 180;
  const pad = { l: 36, r: 4, t: 10, b: 24 };
  const ticks = niceTicks(Math.max(...data.map((d) => d.xp)));
  const top = ticks[ticks.length - 1]!;
  const step = (W - pad.l - pad.r) / data.length;
  const bw = Math.max(6, Math.min(28, step - 6));
  const every = Math.ceil(52 / step); // keep date labels at least ~52px apart
  const [hover, setHover] = useState<number | null>(null);
  const label = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const yv = (v: number) => pad.t + (1 - v / top) * (H - pad.t - pad.b);
  return (
    <div ref={box} className="relative">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block select-none" role="img" aria-label={`${unit} per day for the last ${data.length} days`}>
        {ticks.map((g) => (
          <g key={g}>
            <line x1={pad.l} x2={W - pad.r} y1={yv(g)} y2={yv(g)} stroke={GRID} />
            <text x={pad.l - 6} y={yv(g) + 4} textAnchor="end" fontSize="11" fill={MUTED}>
              {g}
            </text>
          </g>
        ))}
        {data.map((d, i) => {
          const h = (d.xp / top) * (H - pad.t - pad.b);
          const cx = pad.l + step * i + step / 2;
          return (
            <g key={d.day} onPointerEnter={() => setHover(i)} onPointerDown={() => setHover(i)} onPointerLeave={() => setHover(null)}>
              <rect x={cx - step / 2} y={pad.t} width={step} height={H - pad.t - pad.b} fill="transparent" />
              {d.xp > 0 && (
                <path
                  d={`M ${cx - bw / 2} ${H - pad.b} V ${H - pad.b - h + Math.min(4, h)} q 0 -${Math.min(4, h)} ${Math.min(4, h)} -${Math.min(4, h)} H ${cx + bw / 2 - Math.min(4, h)} q ${Math.min(4, h)} 0 ${Math.min(4, h)} ${Math.min(4, h)} V ${H - pad.b} Z`}
                  fill={color}
                  opacity={hover === null || hover === i ? 1 : 0.55}
                />
              )}
              {(data.length - 1 - i) % every === 0 && (
                <text x={cx} y={H - 6} textAnchor="middle" fontSize="11" fill={MUTED}>
                  {label(d.day)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div
          className="pointer-events-none absolute top-0 rounded-chip border border-line bg-surface/95 shadow-lift px-3 py-2 text-xs"
          style={hover > data.length / 2 ? { right: W - (pad.l + step * hover) + 4 } : { left: pad.l + step * (hover + 1) + 4 }}
        >
          <div className="font-semibold">{label(data[hover]!.day)}</div>
          <div className="tabular-nums">
            {data[hover]!.xp} {unit}
          </div>
        </div>
      )}
    </div>
  );
}
