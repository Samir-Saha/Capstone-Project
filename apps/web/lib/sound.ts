// Tiny synthesized sound effects. Off by default; the choice is remembered per browser.

type Cue = "hit" | "miss" | "victory" | "defeat" | "accepted" | "rejected" | "levelup" | "tick";

const KEY = "reps.sound";
let ctx: AudioContext | null = null;

export function soundEnabled(): boolean {
  try {
    return localStorage.getItem(KEY) === "on";
  } catch {
    return false;
  }
}

export function setSoundEnabled(on: boolean) {
  try {
    localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    /* storage blocked: sound stays off next visit */
  }
  window.dispatchEvent(new CustomEvent("reps:sound", { detail: on }));
}

function tone(freq: number, start: number, dur: number, type: OscillatorType, gain = 0.08, slideTo?: number) {
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, ctx.currentTime + start);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, ctx.currentTime + start + dur);
  g.gain.setValueAtTime(0.0001, ctx.currentTime + start);
  g.gain.exponentialRampToValueAtTime(gain, ctx.currentTime + start + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + dur);
  osc.connect(g).connect(ctx.destination);
  osc.start(ctx.currentTime + start);
  osc.stop(ctx.currentTime + start + dur + 0.02);
}

export function play(cue: Cue) {
  if (!soundEnabled() || typeof window === "undefined") return;
  try {
    ctx ??= new AudioContext();
    if (ctx.state === "suspended") void ctx.resume();
  } catch {
    return;
  }
  switch (cue) {
    case "hit":
      tone(520, 0, 0.08, "square", 0.06);
      tone(780, 0.06, 0.14, "square", 0.05, 1040);
      break;
    case "miss":
      tone(220, 0, 0.22, "sawtooth", 0.06, 110);
      break;
    case "victory":
      [523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.11, 0.25, "triangle", 0.08));
      break;
    case "defeat":
      [392, 311, 233].forEach((f, i) => tone(f, i * 0.16, 0.3, "triangle", 0.07));
      break;
    case "accepted":
      tone(660, 0, 0.1, "triangle", 0.08);
      tone(990, 0.1, 0.2, "triangle", 0.08);
      break;
    case "rejected":
      tone(300, 0, 0.18, "square", 0.05, 200);
      break;
    case "levelup":
      [440, 554, 659, 880, 1109].forEach((f, i) => tone(f, i * 0.08, 0.2, "square", 0.05));
      break;
    case "tick":
      tone(1200, 0, 0.03, "sine", 0.03);
      break;
  }
}
