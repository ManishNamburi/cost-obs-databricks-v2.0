import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";

export interface ConversationalStatus {
  configured: boolean;
  space_id?: string;
  reason?: string;
}

export interface ConversationalResponse {
  text: string;
  sql: string;
  columns: string[];
  rows: unknown[][];
}

export interface ConversationalTurn {
  id: string;
  role: "user" | "assistant";
  text: string;
  sql?: string;
  columns?: string[];
  rows?: unknown[][];
  error?: string;
  pending?: boolean;
}

interface Envelope {
  conversation_id: string;
  message_id: string;
  response: ConversationalResponse;
}

async function _postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = (j as { detail?: string }).detail ?? "";
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export function useConversationalStatus() {
  return useQuery<ConversationalStatus>({
    queryKey: ["conversational", "status"],
    queryFn: async () => {
      const res = await fetch("/api/conversational/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useConversational() {
  const [turns, setTurns] = useState<ConversationalTurn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const send = useCallback(
    async (message: string) => {
      if (!message.trim() || isBusy) return;

      const userTurn: ConversationalTurn = {
        id: `u-${Date.now()}`,
        role: "user",
        text: message,
      };
      const pendingTurn: ConversationalTurn = {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: "",
        pending: true,
      };
      setTurns((prev) => [...prev, userTurn, pendingTurn]);
      setIsBusy(true);

      try {
        const body = conversationId
          ? { conversation_id: conversationId, message }
          : { message };
        const url = conversationId
          ? "/api/conversational/reply"
          : "/api/conversational/message";
        const env = await _postJson<Envelope>(url, body);
        setConversationId(env.conversation_id);
        setTurns((prev) => {
          const next = [...prev];
          const idx = next.findIndex((t) => t.id === pendingTurn.id);
          if (idx >= 0) {
            next[idx] = {
              ...pendingTurn,
              pending: false,
              text: env.response.text || "(no answer)",
              sql: env.response.sql || undefined,
              columns: env.response.columns,
              rows: env.response.rows,
            };
          }
          return next;
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setTurns((prev) => {
          const next = [...prev];
          const idx = next.findIndex((t) => t.id === pendingTurn.id);
          if (idx >= 0) {
            next[idx] = { ...pendingTurn, pending: false, text: "", error: msg };
          }
          return next;
        });
      } finally {
        setIsBusy(false);
      }
    },
    [conversationId, isBusy],
  );

  const reset = useCallback(() => {
    setTurns([]);
    setConversationId(null);
  }, []);

  return { turns, isBusy, send, reset };
}
