import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0E1020",
        surface: "#161A2F",
        raised: "#1F2440",
        line: "#2C3256",
        text: "#ECEEFF",
        muted: "#9095BC",
        violet: { DEFAULT: "#8B6CFF", deep: "#5B3FE0", soft: "#B9A8FF" },
        cyan: { DEFAULT: "#3FD8E6", deep: "#1A9FB0" },
        hp: "#FF5C7A",
        heal: "#5BE3A1",
        xp: "#FFC857",
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
      },
      animation: {
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
