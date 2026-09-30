import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#071018",
          900: "#0c1824",
          800: "#132536",
          700: "#1c3348",
          600: "#2a4660",
        },
        sea: {
          300: "#7dd3c0",
          400: "#3db8a0",
          500: "#1f9a82",
          600: "#167a66",
        },
        mist: {
          100: "#e8eef3",
          300: "#a8b8c7",
          500: "#6b7f92",
        },
      },
      boxShadow: {
        soft: "0 18px 50px rgba(0,0,0,0.35)",
        glow: "0 0 24px rgba(61, 184, 160, 0.28)",
        "glow-sm": "0 0 12px rgba(61, 184, 160, 0.2)",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        heartbeat: {
          "0%, 100%": { transform: "scale(1)" },
          "14%": { transform: "scale(1.12)" },
          "28%": { transform: "scale(1)" },
          "42%": { transform: "scale(1.08)" },
          "70%": { transform: "scale(1)" },
        },
        spinSlow: {
          to: { transform: "rotate(360deg)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        fadeUp: "fadeUp 0.5s ease-out both",
        heartbeat: "heartbeat 1.1s ease-in-out infinite",
        spinSlow: "spinSlow 2.4s linear infinite",
        pulseGlow: "pulseGlow 1.8s ease-in-out infinite",
      },
      fontFamily: {
        display: ["var(--font-fraunces)", "Georgia", "serif"],
        sans: ["var(--font-manrope)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
