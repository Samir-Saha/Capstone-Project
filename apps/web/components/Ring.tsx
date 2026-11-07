/** Progress ring. value is 0..1, or null when there's nothing measured yet. */
export function Ring({ value, label, sub, color }: { value: number | null; label: string; sub: string; color: string }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const v = value === null ? 0 : Math.max(0, Math.min(1, value));
  return (
    <figure className="flex flex-col items-center text-center">
      <div className="relative h-24 w-24">
        <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90" aria-hidden>
          <circle cx="40" cy="40" r={r} fill="none" stroke="rgb(var(--line))" strokeWidth="7" />
          <circle
            cx="40"
            cy="40"
            r={r}
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={`${c * v} ${c}`}
            className="transition-[stroke-dasharray] duration-700 ease-out"
            style={{ filter: `drop-shadow(0 0 6px ${color})` }}
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center font-pixel text-xl tabular-nums">{value === null ? "–" : `${Math.round(v * 100)}%`}</span>
      </div>
      <figcaption className="mt-2 text-sm font-medium leading-tight">
        {label}
        <span className="block text-xs font-normal text-muted">{sub}</span>
      </figcaption>
    </figure>
  );
}
