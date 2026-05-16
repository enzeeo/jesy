import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // From DESIGN.md (Pass 5 of /plan-design-review)
        "sev-immediate": "#EF4444",
        "sev-delayed": "#FACC15",
        "sev-minor": "#22C55E",
        "sev-deceased": "#1F2937",
        "bg-base": "#0B0F19",
        "bg-panel": "#0F172A",
        "bg-elev": "#1E293B",
        "border-strong": "#334155",
        "fg-primary": "#F1F5F9",
        "fg-secondary": "#94A3B8",
        "fg-muted": "#64748B",
        "status-good": "#10B981",
        "status-warn": "#F59E0B",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui"],
      },
      borderRadius: {
        DEFAULT: "2px",
        "panel": "0px",
        "tile": "4px",
      },
      keyframes: {
        "severity-halo": {
          "0%": { transform: "scale(1)", opacity: "1" },
          "100%": { transform: "scale(4)", opacity: "0" },
        },
        "severity-pulse": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.4" },
        },
        "toast-slide-in": {
          "0%": { transform: "translateX(100%)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
      },
      animation: {
        "severity-halo": "severity-halo 200ms ease-out forwards",
        "severity-pulse": "severity-pulse 666ms ease-in-out 3",
        "toast-slide-in": "toast-slide-in 200ms ease-out",
      },
    },
  },
  plugins: [],
};
export default config;
