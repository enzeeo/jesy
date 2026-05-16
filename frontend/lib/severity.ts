// Single source of truth for severity visual encoding (Code Quality issue 2.7).
// Used by: map symbols, incident list rows, infra panel chips, after-action mode.

import type { Severity } from "./types";

export const SEVERITY_VISUAL: Record<Severity, {
  color: string;
  shape: "circle" | "square" | "triangle" | "circle-x";
  label: string;
  a11y: string;
  haloColor: string;
}> = {
  Immediate: {
    color: "#EF4444",
    shape: "circle",
    label: "IMMEDIATE",
    a11y: "Immediate severity, life-threatening",
    haloColor: "#FCA5A5",
  },
  Delayed: {
    color: "#FACC15",
    shape: "square",
    label: "DELAYED",
    a11y: "Delayed severity, serious but stable",
    haloColor: "#FDE68A",
  },
  Minor: {
    color: "#22C55E",
    shape: "triangle",
    label: "MINOR",
    a11y: "Minor severity, walking wounded",
    haloColor: "#86EFAC",
  },
  Deceased: {
    color: "#1F2937",
    shape: "circle-x",
    label: "DECEASED",
    a11y: "Deceased, no resources required",
    haloColor: "#FFFFFF",
  },
};

export const ALL_SEVERITIES: Severity[] = ["Immediate", "Delayed", "Minor", "Deceased"];
