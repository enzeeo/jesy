"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ChatMessage, ChatSession } from "@/lib/types";

interface Props {
  incidentId?: string | null;
  sector?: string | null;
  collapsed?: boolean;
  onToggle?: () => void;
}

export function CortexChat({ incidentId, sector, collapsed = false, onToggle }: Props) {
  const [session, setSession] = useState<ChatSession | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const ensureSession = useCallback(async () => {
    if (session) return session;
    const scope = incidentId ? "incident" : sector ? "sector" : "global";
    const scopeRef = incidentId ?? sector ?? undefined;
    const created = await api.createChatSession({
      scope,
      scope_ref_id: scopeRef,
    });
    setSession(created);
    return created;
  }, [session, incidentId, sector]);

  useEffect(() => {
    setSession(null);
  }, [incidentId, sector]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setLoading(true);
    setError(null);
    setInput("");
    try {
      const s = await ensureSession();
      const res = await api.postChatMessage(s.session_id, {
        message: text,
        context: {
          incident_id: incidentId ?? undefined,
          sector: sector ?? undefined,
        },
      });
      setSession(res.session);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chat failed");
    } finally {
      setLoading(false);
    }
  }

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="absolute bottom-4 left-4 z-20 mono border border-border-strong bg-bg-panel px-3 py-2 text-xs font-bold uppercase text-fg-primary shadow-lg hover:bg-bg-elev"
      >
        Cortex chat
      </button>
    );
  }

  return (
    <div className="absolute bottom-4 left-4 z-20 flex h-[min(420px,55vh)] w-80 flex-col border border-border-strong bg-bg-panel shadow-2xl">
      <div className="flex items-center justify-between border-b border-border-strong px-3 py-2">
        <div>
          <div className="mono text-xs uppercase tracking-wider text-fg-secondary">Cortex chat</div>
          <div className="text-xs text-fg-muted">
            {incidentId ? `incident ${incidentId.slice(0, 8)}…` : sector ? `sector ${sector}` : "global"}
          </div>
        </div>
        {onToggle ? (
          <button type="button" onClick={onToggle} className="text-fg-muted hover:text-fg-primary" aria-label="Collapse">—</button>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {(session?.messages ?? []).length === 0 && (
          <p className="text-xs text-fg-muted p-1">
            Ask about open incidents, dispatches, sector load, or injuries.
          </p>
        )}
        {(session?.messages ?? []).map((m, i) => (
          <MessageBubble key={`${m.created_at}-${i}`} message={m} />
        ))}
        {loading ? (
          <div className="mono text-xs text-fg-muted animate-pulse">Thinking…</div>
        ) : null}
        <div ref={bottomRef} />
      </div>

      {error ? <div className="mono px-2 pb-1 text-xs text-status-warn">{error}</div> : null}

      <div className="border-t border-border-strong p-2 flex gap-1">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send())}
          placeholder="Ask dispatch…"
          disabled={loading}
          className="flex-1 border border-border-strong bg-bg-base px-2 py-1.5 text-xs text-fg-primary placeholder:text-fg-muted focus:outline-none"
        />
        <button
          type="button"
          disabled={loading || !input.trim()}
          onClick={send}
          className="mono border border-border-strong px-2 py-1 text-xs font-bold uppercase hover:bg-bg-elev disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={isUser ? "text-right" : "text-left"}>
      <div
        className={`inline-block max-w-full text-left px-2 py-1.5 text-xs ${
          isUser ? "bg-bg-elev text-fg-primary" : "border border-border-strong text-fg-secondary"
        }`}
      >
        {message.content}
      </div>

    </div>
  );
}
