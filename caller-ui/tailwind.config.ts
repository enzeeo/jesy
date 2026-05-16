import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
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
        panel: "0px",
        tile: "4px",
      },
    },
  },
  plugins: [],
};

export default config;
