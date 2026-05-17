// Thin types + helpers for the ElevenLabs Conversational AI widget.
//
// The widget exposes a custom element <elevenlabs-convai> registered by the
// script loaded in app/layout.tsx. We pass agent id + overrides via attributes
// and subscribe to its events with addEventListener.
//
// We keep this surface minimal — the widget package's TypeScript types aren't
// stable, so we hand-roll the shape we actually use. If they ship typed events
// upstream later, swap to their types.

export type CallStatusChip =
  | "incident_created"
  | "assessment_updated"
  | "resources_checked"
  | "finalized";

export interface ToolCallEvent {
  /** Name of the server tool the agent invoked. */
  tool_name: string;
  /** JSON args the agent sent. */
  parameters?: Record<string, unknown>;
  /** Response the backend returned. */
  result?: Record<string, unknown>;
}

export interface AgentMessageEvent {
  message: string;
  source: "agent" | "user";
}

const INCIDENT_ID_KEY = "disaster.caller.active_incident_id";
const CONVERSATION_ID_KEY = "disaster.caller.active_conversation_id";

export function rememberIncidentId(id: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(INCIDENT_ID_KEY, id);
  } catch {
    // sessionStorage may throw in private browsing — recovery is best-effort
  }
}

export function recallIncidentId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(INCIDENT_ID_KEY);
  } catch {
    return null;
  }
}

export function clearIncidentId(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(INCIDENT_ID_KEY);
    window.sessionStorage.removeItem(CONVERSATION_ID_KEY);
  } catch {
    // ignore
  }
}

export function newConversationId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `conv-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;
}

/**
 * Map a server-tool name to the chip we want to show on the call panel.
 * Returns null for tools we don't surface visually.
 */
export function chipForToolName(toolName: string): CallStatusChip | null {
  switch (toolName) {
    case "create_incident_provisional":
      return "incident_created";
    case "update_assessment":
      return "assessment_updated";
    case "query_nearby_resources":
      return "resources_checked";
    case "finalize":
      return "finalized";
    default:
      return null;
  }
}
