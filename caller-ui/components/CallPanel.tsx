"use client";

import { useConversation } from "@elevenlabs/react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  type CallStatusChip,
  chipForToolName,
  clearIncidentId,
  rememberIncidentId,
} from "@/lib/elevenlabs";

interface CallPanelProps {
  agentId: string;
  conversationId: string;
  lat: number;
  lng: number;
  deviceId: string;
  geoSource: "gps" | "fallback";
}

const CHIP_LABEL: Record<CallStatusChip, string> = {
  incident_created: "Incident created",
  assessment_updated: "Assessment updated",
  resources_checked: "Resources checked",
  finalized: "Call finalized",
};

const CHIP_ORDER: CallStatusChip[] = [
  "incident_created",
  "assessment_updated",
  "resources_checked",
  "finalized",
];

interface ToolRequest {
  tool_call_id: string;
  tool_name: string;
}

interface ToolResponseFull {
  tool_call_id: string;
  tool_name: string;
  full_tool_result?: string;
  is_error?: boolean;
}

/**
 * Custom voice UI. Subscribes to ElevenLabs Conversational AI via
 * useConversation hook, runs an rAF loop polling input/output volumes,
 * renders an animated pulse ring, captions, tool-call chips, mute, and
 * end-call. Navigates to /status/{incident_id} once we have one.
 */
export function CallPanel({
  agentId,
  conversationId,
  lat,
  lng,
  deviceId,
  geoSource,
}: CallPanelProps) {
  const router = useRouter();

  const [chips, setChips] = useState<Set<CallStatusChip>>(new Set());
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [caption, setCaption] = useState<{ text: string; role: "user" | "agent" } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [hasEnded, setHasEnded] = useState(false);

  // The rAF loop reads volume into refs (not state) every frame to avoid
  // re-renders. The ring transform reads the ref directly via inline style
  // updates on a single rAF tick.
  const ringRef = useRef<HTMLDivElement | null>(null);
  const captionRef = useRef<HTMLParagraphElement | null>(null);

  // Track in-flight tool calls by tool_call_id so we can match request → response.
  const pendingToolsRef = useRef<Map<string, ToolRequest>>(new Map());

  const conversation = useConversation({
    onConnect: ({ conversationId: convId }) => {
      console.log("[CallPanel] connected", convId);
    },
    onStatusChange: ({ status }) => {
      console.log("[CallPanel] status →", status);
    },
    onDisconnect: (details) => {
      console.log("[CallPanel] disconnected", details);
      setHasEnded(true);
    },
    onMessage: ({ message, role }) => {
      if (typeof message === "string" && message.trim().length > 0) {
        setCaption({ text: message, role: role === "agent" ? "agent" : "user" });
      }
    },
    onError: (msg, context) => {
      console.error("[CallPanel] error", msg, context);
      setErrorMsg(typeof msg === "string" ? msg : JSON.stringify(msg));
    },
    onAgentToolRequest: (req) => {
      // Light-up the chip the moment the agent fires the tool, not when it returns.
      // Feels more responsive on the dispatcher's side.
      pendingToolsRef.current.set(req.tool_call_id, {
        tool_call_id: req.tool_call_id,
        tool_name: req.tool_name,
      });
      const chip = chipForToolName(req.tool_name);
      if (chip) {
        setChips((prev) => {
          if (prev.has(chip)) return prev;
          const next = new Set(prev);
          next.add(chip);
          return next;
        });
      }
    },
    onAgentToolResponse: (resp) => {
      // The "full payload" variant carries the actual JSON result.
      // The plain variant only carries metadata. Try the rich path first.
      const full = resp as Partial<ToolResponseFull>;
      const req = full.tool_call_id ? pendingToolsRef.current.get(full.tool_call_id) : undefined;
      const toolName = full.tool_name ?? req?.tool_name;

      if (toolName === "create_incident_provisional" && full.full_tool_result) {
        try {
          const parsed = JSON.parse(full.full_tool_result) as { incident_id?: string };
          if (parsed.incident_id) {
            setIncidentId(parsed.incident_id);
            rememberIncidentId(parsed.incident_id);
            console.log("[CallPanel] captured incident_id", parsed.incident_id);
          }
        } catch (e) {
          console.warn("[CallPanel] could not parse tool result", e);
        }
      }
    },
  });

  // Start the session once on mount. Pass dynamic variables so the agent's
  // {{conversation_id}}, {{caller_lat}} etc resolve to real values per call.
  const sessionStartedRef = useRef(false);
  useEffect(() => {
    if (sessionStartedRef.current) return;
    sessionStartedRef.current = true;

    void conversation.startSession({
      agentId,
      // WebSocket transport instead of default WebRTC — iOS Safari WebRTC
      // chronically fails the LocalTrackSubscribed handshake on first call,
      // leaving the session stuck in "connecting". WebSocket is more reliable
      // for mobile + tunneled environments at the cost of slightly higher
      // audio latency.
      connectionType: "websocket",
      dynamicVariables: {
        // Match placeholder types in agent config (all strings) so the agent's
        // template-render step doesn't reject the session.
        conversation_id: conversationId,
        caller_lat: String(lat),
        caller_lng: String(lng),
        device_id: deviceId,
        geo_source: geoSource,
      },
    });

    return () => {
      try {
        conversation.endSession();
      } catch {
        // already ended, ignore
      }
    };
    // intentionally only depend on agentId/conversationId — props are stable per route nav
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, conversationId]);

  // Audio-reactive ring: rAF loop reads volumes and updates a CSS variable.
  // We avoid re-rendering React on every frame.
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const ring = ringRef.current;
      if (ring) {
        const isAgentTurn = conversation.isSpeaking;
        let level = 0;
        try {
          level = isAgentTurn ? conversation.getOutputVolume() : conversation.getInputVolume();
        } catch {
          level = 0;
        }
        const scale = 1 + Math.min(level, 1) * 0.45;
        ring.style.setProperty("--ring-scale", scale.toFixed(3));
        ring.style.setProperty(
          "--ring-color",
          isAgentTurn ? "var(--sev-immediate, #EF4444)" : "var(--status-good, #10B981)",
        );
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [conversation]);

  // Navigate to /status once the call ends and we have an incident id.
  useEffect(() => {
    if (!hasEnded) return;
    if (incidentId) {
      router.push(`/status/${incidentId}`);
    } else {
      clearIncidentId();
      router.push("/");
    }
  }, [hasEnded, incidentId, router]);

  const statusLabel = useMemo(() => {
    switch (conversation.status) {
      case "connecting":
        return "Connecting";
      case "connected":
        return conversation.isSpeaking ? "Agent speaking" : "Listening";
      case "disconnected":
        return "Call ended";
      default:
        return conversation.status;
    }
  }, [conversation.status, conversation.isSpeaking]);

  const statusColor = useMemo(() => {
    if (conversation.status === "connected") return "text-status-good";
    if (conversation.status === "connecting") return "text-status-warn";
    return "text-fg-secondary";
  }, [conversation.status]);

  return (
    <section className="border border-border-strong bg-bg-panel p-5">
      <header className="flex items-center justify-between gap-2">
        <p className="mono text-xs uppercase tracking-[0.16em] text-fg-muted">Voice call</p>
        <div className="flex items-center gap-2">
          <span className="mono text-[10px] uppercase tracking-[0.16em] text-fg-muted">
            ({conversation.status})
          </span>
          <span
            aria-live="polite"
            className={`mono text-xs uppercase tracking-[0.16em] ${statusColor}`}
          >
            {statusLabel}
          </span>
        </div>
      </header>

      {/* Audio-reactive pulse ring */}
      <div className="mt-8 flex items-center justify-center">
        <div className="relative h-44 w-44">
          {/* Outer pulsing ring — scales with current speaker's volume */}
          <div
            ref={ringRef}
            aria-hidden
            className="absolute inset-0 rounded-full border-2 transition-colors"
            style={{
              borderColor: "var(--ring-color, #10B981)",
              transform: "scale(var(--ring-scale, 1))",
              transitionProperty: "transform, border-color",
              transitionDuration: "60ms",
              transitionTimingFunction: "ease-out",
              boxShadow: "0 0 24px -8px var(--ring-color, #10B981)",
            }}
          />
          {/* Static inner disc */}
          <div className="absolute inset-6 flex items-center justify-center rounded-full bg-bg-elev">
            <span className="mono text-lg font-semibold text-fg-primary">
              {conversation.isSpeaking ? "AI" : conversation.status === "connected" ? "YOU" : "..."}
            </span>
          </div>
        </div>
      </div>

      {/* Live caption strip */}
      <div className="mt-8 min-h-20 border border-border-strong bg-bg-base p-4">
        {caption ? (
          <>
            <p className="mono text-[10px] uppercase tracking-[0.16em] text-fg-muted">
              {caption.role === "agent" ? "Assistant" : "You said"}
            </p>
            <p
              ref={captionRef}
              className={`mt-1 text-base leading-6 ${
                caption.role === "agent" ? "text-fg-primary" : "text-fg-secondary"
              }`}
            >
              {caption.text}
            </p>
          </>
        ) : (
          <p className="text-sm italic text-fg-secondary">
            Speak naturally. The assistant will hear you and respond.
          </p>
        )}
      </div>

      {/* Tool-call status chips */}
      {chips.size > 0 && (
        <ul className="mt-4 grid gap-2">
          {CHIP_ORDER.filter((chip) => chips.has(chip)).map((chip) => (
            <li
              key={chip}
              className="border border-status-good/40 bg-status-good/10 px-3 py-2 text-sm text-emerald-100"
            >
              ✓ {CHIP_LABEL[chip]}
            </li>
          ))}
        </ul>
      )}

      {/* Error display */}
      {errorMsg && (
        <p className="mt-4 border border-sev-immediate/40 bg-sev-immediate/10 p-3 text-sm text-rose-100">
          {errorMsg}
        </p>
      )}

      {/* Controls */}
      <div className="mt-8 grid grid-cols-[1fr_2fr] gap-3">
        <button
          type="button"
          onClick={() => conversation.setMuted(!conversation.isMuted)}
          disabled={conversation.status !== "connected"}
          className="touch-manipulation select-none min-h-14 border border-border-strong bg-bg-panel px-4 py-3 text-base font-semibold text-fg-primary hover:bg-bg-elev disabled:opacity-50"
        >
          {conversation.isMuted ? "Unmute" : "Mute"}
        </button>
        <button
          type="button"
          onClick={() => {
            try {
              conversation.endSession();
            } catch {
              // already ended
            }
            setHasEnded(true);
          }}
          className="touch-manipulation select-none min-h-14 bg-sev-immediate px-4 py-3 text-base font-semibold text-white"
        >
          End call
        </button>
      </div>

      {geoSource === "fallback" && (
        <p className="mono mt-4 text-xs uppercase tracking-[0.16em] text-status-warn">
          Using default location — GPS unavailable
        </p>
      )}
    </section>
  );
}
