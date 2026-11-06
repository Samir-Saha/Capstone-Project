import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "rgb(var(--ink) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        raised: "rgb(var(--raised) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        text: "rgb(var(--text) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        night: "#14162B", // dark text on bright buttons, same in every theme
        violet: { DEFAULT: "rgb(var(--violet) / <alpha-value>)", deep: "rgb(var(--violet-deep) / <alpha-value>)", soft: "rgb(var(--violet-soft) / <alpha-value>)" },
        cyan: { DEFAULT: "rgb(var(--cyan) / <alpha-value>)", deep: "rgb(var(--cyan-deep) / <alpha-value>)" },
        hp: "rgb(var(--hp) / <alpha-value>)",
        heal: "rgb(var(--heal) / <alpha-value>)",
        xp: "rgb(var(--xp) / <alpha-value>)",
        sun: "rgb(var(--sun) / <alpha-value>)", // bright amber fill for buttons and bars
      },
      boxShadow: {
        card: "0 1px 2px rgb(0 0 0 / 0.3), 0 6px 20px -8px rgb(0 0 0 / 0.5)",
        lift: "0 2px 4px rgb(0 0 0 / 0.3), 0 14px 32px -10px rgb(139 92 246 / 0.35)",
      },
      fontFamily: {
        display: ['"Chakra Petch"', "system-ui", "sans-serif"],
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      borderRadius: { panel: "14px", chip: "6px" },
      keyframes: {
        float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-10px)" } },
        hit: {
          "0%": { transform: "translateX(0)", filter: "brightness(1)" },
          "20%": { transform: "translateX(-10px)", filter: "brightness(2.2)" },
          "40%": { transform: "translateX(8px)" },
          "60%": { transform: "translateX(-5px)" },
          "100%": { transform: "translateX(0)", filter: "brightness(1)" },
        },
        lunge: {
          "0%": { transform: "scale(1)" },
          "35%": { transform: "scale(1.12) translateY(14px)" },
          "100%": { transform: "scale(1)" },
        },
        shake: {
          "0%,100%": { transform: "translate(0,0)" },
          "25%": { transform: "translate(-6px,3px)" },
          "50%": { transform: "translate(5px,-3px)" },
          "75%": { transform: "translate(-3px,2px)" },
        },
        rise: {
          "0%": { opacity: "0", transform: "translateY(8px) scale(0.9)" },
          "15%": { opacity: "1", transform: "translateY(0) scale(1.1)" },
          "100%": { opacity: "0", transform: "translateY(-56px) scale(1)" },
        },
        pop: { "0%": { transform: "scale(0.85)", opacity: "0" }, "100%": { transform: "scale(1)", opacity: "1" } },
        pulse_ring: { "0%": { transform: "scale(0.9)", opacity: "0.7" }, "100%": { transform: "scale(1.5)", opacity: "0" } },
        // shards fly outward along --dx/--dy, set per shard
        burst: {
          "0%": { transform: "translate(-50%,-50%) translate(0,0) rotate(0deg) scale(1)", opacity: "1" },
          "100%": { transform: "translate(-50%,-50%) translate(var(--dx),var(--dy)) rotate(var(--rot)) scale(0.2)", opacity: "0" },
        },
        flash: {
          "0%": { opacity: "0.9", transform: "translate(-50%,-50%) scale(0.4)" },
          "100%": { opacity: "0", transform: "translate(-50%,-50%) scale(1.6)" },
        },
        vignette: { "0%": { opacity: "0" }, "20%": { opacity: "1" }, "100%": { opacity: "0" } },
        heartbreak: {
          "0%": { transform: "scale(1)", opacity: "1" },
          "25%": { transform: "scale(1.45)", opacity: "1" },
          "100%": { transform: "translateY(18px) rotate(-25deg) scale(0.6)", opacity: "0" },
        },
        enter: { "0%": { opacity: "0", transform: "translateY(14px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        windup: {
          "0%": { transform: "translateY(0) scale(1)" },
          "40%": { transform: "translateY(-14px) scale(0.94)" },
          "70%": { transform: "translateY(6px) scale(1.06)" },
          "100%": { transform: "translateY(0) scale(1)" },
        },
        shatter: {
          "0%": { transform: "scale(1)", filter: "brightness(1) blur(0)", opacity: "1" },
          "15%": { transform: "scale(1.12)", filter: "brightness(2.5) blur(0)", opacity: "1" },
          "100%": { transform: "scale(0.7) translateY(30px)", filter: "brightness(0.6) blur(6px) grayscale(1)", opacity: "0.25" },
        },
        loom: { "0%": { transform: "scale(1)" }, "100%": { transform: "scale(1.1) translateY(-6px)" } },
        stamp: {
          "0%": { transform: "scale(1.9) rotate(-8deg)", opacity: "0" },
          "60%": { transform: "scale(0.95) rotate(1deg)", opacity: "1" },
          "100%": { transform: "scale(1) rotate(0)", opacity: "1" },
        },
        glow: {
          "0%": { boxShadow: "0 0 0 0 rgba(255,200,87,0)" },
          "30%": { boxShadow: "0 0 14px 3px rgba(255,200,87,0.75)" },
          "100%": { boxShadow: "0 0 0 0 rgba(255,200,87,0)" },
        },
        ignite: { "0%": { transform: "scale(1)" }, "40%": { transform: "scale(1.35)" }, "100%": { transform: "scale(1)" } },
        breathe: { "0%,100%": { opacity: "0.45" }, "50%": { opacity: "1" } },
      },
      animation: {
        burst: "burst 700ms cubic-bezier(.15,.7,.3,1) forwards",
        flash: "flash 450ms ease-out forwards",
        vignette: "vignette 650ms ease-out forwards",
        heartbreak: "heartbreak 650ms ease-in forwards",
        enter: "enter 260ms cubic-bezier(.2,.8,.3,1) both",
        windup: "windup 520ms cubic-bezier(.3,.7,.3,1)",
        shatter: "shatter 1100ms ease-out forwards",
        loom: "loom 900ms ease-out forwards",
        stamp: "stamp 420ms cubic-bezier(.2,.9,.3,1.2) both",
        glow: "glow 900ms ease-out",
        ignite: "ignite 380ms ease-out",
        breathe: "breathe 1.4s ease-in-out infinite",
        float: "float 5s ease-in-out infinite",
        hit: "hit 450ms ease-out",
        lunge: "lunge 500ms ease-in-out",
        shake: "shake 320ms ease-in-out",
        rise: "rise 1.2s ease-out forwards",
        pop: "pop 220ms cubic-bezier(.2,.9,.3,1.3)",
        pulse_ring: "pulse_ring 1.6s ease-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
