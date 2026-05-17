"use client";

import { ConversationProvider } from "@elevenlabs/react";
import type { ReactNode } from "react";

/**
 * Wraps the app in ElevenLabs's ConversationProvider so any descendant
 * component can call useConversation. Per their React SDK, the provider is
 * required for the hook to work — without it the hook errors at first render.
 *
 * No default agentId / options — the call screen passes those to
 * startSession() with the actual per-call context.
 */
export function ConversationShell({ children }: { children: ReactNode }) {
  return <ConversationProvider>{children}</ConversationProvider>;
}
