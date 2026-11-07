// Original pixel-art backdrops drawn from rectangles. viewBox units are "pixels";
// crispEdges keeps every block sharp at any size.

type R = [x: number, y: number, w: number, h: number];

const STARS: R[] = [
  [8, 4, 1, 1], [21, 9, 1, 1], [33, 3, 1, 1], [47, 7, 1, 1], [62, 2, 1, 1], [75, 10, 1, 1], [88, 5, 1, 1],
  [101, 2, 1, 1], [117, 8, 1, 1], [129, 3, 1, 1], [171, 4, 1, 1], [183, 10, 1, 1], [56, 13, 1, 1], [12, 15, 1, 1],
];

// A castle silhouette: keep, two towers with crenellations, a gate.
const CASTLE: R[] = [
  [140, 24, 40, 24], // curtain wall
  [146, 14, 9, 34], // left tower
  [165, 10, 11, 38], // right tower
  [154, 18, 12, 30], // keep
  [146, 12, 2, 2], [149, 12, 2, 2], [152, 12, 3, 2],
  [165, 8, 2, 2], [168, 8, 2, 2], [171, 8, 2, 2], [174, 8, 2, 2],
  [154, 16, 2, 2], [157, 16, 2, 2], [160, 16, 2, 2], [163, 16, 3, 2],
  [140, 22, 2, 2], [143, 22, 2, 2], [178, 22, 2, 2],
  [169, 4, 1, 4], // flag pole
  [170, 4, 3, 2], // flag
];

const HILLS: R[] = [
  [0, 40, 192, 8], [0, 36, 30, 4], [6, 33, 16, 3], [30, 38, 26, 2], [96, 37, 40, 3], [104, 35, 22, 2], [184, 38, 8, 2],
];

const CLOUDS: R[] = [
  [18, 20, 26, 2], [14, 22, 36, 2], [22, 18, 14, 2],
  [92, 14, 22, 2], [86, 16, 34, 2], [96, 12, 10, 2],
  [118, 28, 30, 2], [112, 30, 42, 2],
];

function Rects({ rects, fill }: { rects: R[]; fill: string }) {
  return (
    <>
      {rects.map(([x, y, w, h], i) => (
        <rect key={i} x={x} y={y} width={w} height={h} fill={fill} />
      ))}
    </>
  );
}

/** Wide quest banner: dusk sky, moon, clouds, a castle on the hill. */
export function QuestBanner({ className = "" }: { className?: string }) {
  // 300x48 matches a wide banner, so nothing gets cropped; the scene sits on the right
  // and the left stays open sky for the text.
  return (
    <svg viewBox="0 0 300 48" preserveAspectRatio="xMaxYMax slice" shapeRendering="crispEdges" className={className} aria-hidden>
      <defs>
        <linearGradient id="qb-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#1E1250" />
          <stop offset="0.55" stopColor="#4C2491" />
          <stop offset="1" stopColor="#B4549B" />
        </linearGradient>
      </defs>
      <rect width="300" height="48" fill="url(#qb-sky)" />
      <Rects rects={STARS} fill="#F5E9FF" />
      <g transform="translate(108 0)">
        <Rects rects={STARS} fill="#F5E9FF" />
        {/* moon */}
        <Rects rects={[[156, 6, 8, 1], [154, 7, 12, 1], [153, 8, 14, 6], [154, 14, 12, 1], [156, 15, 8, 1]]} fill="#F6C9E8" />
        <Rects rects={[[158, 9, 3, 2], [162, 12, 2, 1]]} fill="#E3A9D3" />
        <Rects rects={CLOUDS} fill="#8E4FB8" />
        <Rects rects={CLOUDS.map(([x, y, w]) => [x + 2, y, w - 6, 1] as R)} fill="#B67AD6" />
        <Rects rects={CASTLE.map(([x, y, w, h]) => [x - 10, y + 4, w, h] as R)} fill="#170C38" />
        <Rects rects={[[149, 30, 2, 3], [158, 22, 2, 3], [139, 24, 2, 2]]} fill="#FBBF24" />
        <Rects rects={[[147, 44, 6, 4]]} fill="#0D0724" />
      </g>
      <Rects rects={[[-20, 26, 0, 0], [40, 24, 30, 2], [34, 26, 44, 2]]} fill="#6B3AA0" />
      <Rects rects={HILLS} fill="#120A2C" />
      <Rects rects={HILLS.map(([x, y, w, h]) => [x + 108, y, w, h] as R)} fill="#120A2C" />
    </svg>
  );
}

/** Boss arena: violet haze, rock spires and two pillars framing the fight. */
export function ArenaStage({ className = "" }: { className?: string }) {
  const pillar = (x: number, tall: boolean): R[] => {
    const top = tall ? 22 : 40;
    return [
      [x - 2, top, 12, 3],
      [x, top + 3, 8, 3],
      [x + 1, top + 6, 6, 70 - top - 6],
      [x - 1, 66, 10, 3],
      [x - 3, 69, 14, 4],
    ];
  };
  return (
    <svg viewBox="0 0 120 80" preserveAspectRatio="xMidYMax slice" shapeRendering="crispEdges" className={className} aria-hidden>
      <defs>
        <radialGradient id="as-glow" cx="0.3" cy="0.1" r="0.9">
          <stop offset="0" stopColor="#E88BF2" />
          <stop offset="0.45" stopColor="#8B5CF6" />
          <stop offset="1" stopColor="#2A1A5E" />
        </radialGradient>
      </defs>
      <rect width="120" height="80" fill="url(#as-glow)" />
      {/* distant spires */}
      <Rects rects={[[18, 30, 10, 44], [20, 26, 6, 4], [22, 22, 3, 4], [84, 24, 12, 50], [86, 18, 8, 6], [89, 12, 3, 6], [52, 36, 14, 38], [55, 30, 8, 6]]} fill="#6E4BC4" />
      <Rects rects={[[24, 34, 1, 20], [90, 30, 1, 24], [60, 40, 1, 18]]} fill="#5A3AAE" />
      {/* pillars */}
      <Rects rects={[...pillar(4, true), ...pillar(108, true), ...pillar(18, false), ...pillar(94, false)]} fill="#120A24" />
      {/* floor */}
      <rect x="0" y="73" width="120" height="7" fill="#120A24" />
      <Rects rects={[[0, 73, 120, 1]]} fill="#3B2A73" />
    </svg>
  );
}
