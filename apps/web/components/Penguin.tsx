// Reps' mascot: an original pixel penguin in a graduation cap and a red cape.
// Each string is one row of pixels; each letter maps to a color below.

const ROWS = [
  "....CCCCCCCCCCCC....",
  "..CCCCCCCCCCCCCCCC..",
  "....CCCCCCCCCCCCcG..",
  ".....cKKKKKKKKKc.G..",
  "....KKKKKKKKKKKK.GG.",
  "...KKKWWWKKWWWKKK...",
  "...KKWWPWWWWPWWKK...",
  "...KKWWWWWWWWWWKK...",
  "...KKKWWOOOOWWKKK...",
  "..RKKKKWWWOOWWKKK...",
  ".RRKKKWWWWWWWWKKKK..",
  "RRRKKWWWWWWWWWWKKK..",
  "RRKKKWWWWWWWWWWKKKK.",
  "RRKKWWWWWWWWWWWWKKK.",
  "RrKKWWWWWWWWWWWWKK..",
  "RrKKWWWWWWWWWWWWKK..",
  "rrKKKWWWWWWWWWWKKK..",
  "rr.KKKWWWWWWWWKKK...",
  "r...KKKKKKKKKKKK....",
  "....OOOO....OOOO....",
];

const COLORS: Record<string, string> = {
  C: "#2E2A6B", // cap
  c: "#1F1B4F", // cap shadow
  G: "#FBBF24", // tassel
  K: "#141127", // feathers
  W: "#F5F3FF", // belly and face
  P: "#141127", // pupils
  O: "#F59E0B", // beak and feet
  R: "#E11D48", // cape
  r: "#9F1239", // cape shadow
};

export function Penguin({ className = "", bob = false }: { className?: string; bob?: boolean }) {
  const rects: { x: number; y: number; w: number; fill: string }[] = [];
  ROWS.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      const ch = row.charAt(x);
      let w = 1;
      while (x + w < row.length && row[x + w] === ch) w++;
      const fill = COLORS[ch];
      if (fill) rects.push({ x, y, w, fill });
      x += w;
    }
  });
  return (
    <svg viewBox="0 0 20 20" shapeRendering="crispEdges" className={`${bob ? "animate-float" : ""} ${className}`} aria-hidden>
      {rects.map((r, i) => (
        <rect key={i} x={r.x} y={r.y} width={r.w} height={1} fill={r.fill} />
      ))}
    </svg>
  );
}
