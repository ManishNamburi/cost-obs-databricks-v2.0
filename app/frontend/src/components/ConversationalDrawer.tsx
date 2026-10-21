import { useEffect, useRef, useState } from "react";
import { useConversational, useConversationalStatus } from "@/hooks/useConversational";
import type { ConversationalTurn } from "@/hooks/useConversational";

interface ConversationalDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function ConversationalDrawer({ open, onClose }: ConversationalDrawerProps) {
  const { data: status } = useConversationalStatus();
  const { turns, isBusy, send, reset } = useConversational();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns.length, isBusy]);

  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [open, onClose]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isBusy) return;
    void send(input.trim());
    setInput("");
  };

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-[9998] bg-black/20 transition-opacity"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        className={`fixed right-0 top-0 z-[9999] flex h-full w-full max-w-md flex-col border-l border-gray-200 bg-white shadow-xl transition-transform duration-200 ease-out ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        role="dialog"
        aria-label="Ask Genie"
      >
        <header className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-[#FF3621]" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-gray-900">Ask Genie</h2>
            {status?.configured === false && (
              <span className="ml-2 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-200">
                Not configured
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {turns.length > 0 && (
              <button
                type="button"
                onClick={reset}
                className="rounded px-2 py-1 text-xs font-medium text-gray-500 hover:bg-gray-100 hover:text-gray-700"
              >
                New chat
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
              aria-label="Close"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </header>

        {status?.configured === false ? (
          <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-gray-600">
            <div>
              <p className="mb-2 font-medium text-gray-900">Genie space not configured.</p>
              <p>
                The setup job creates this Genie space on deploy. After that
                step finishes, refresh this panel.
              </p>
              {status.reason && (
                <p className="mt-3 text-xs text-gray-500">Reason: {status.reason}</p>
              )}
            </div>
          </div>
        ) : (
          <>
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4">
              {turns.length === 0 ? (
                <EmptyState onPick={(q) => { setInput(q); }} />
              ) : (
                <div className="space-y-4">
                  {turns.map((t) => (
                    <TurnBubble key={t.id} turn={t} onFollowUp={(q) => { setInput(q); }} />
                  ))}
                </div>
              )}
            </div>

            <form onSubmit={handleSubmit} className="border-t border-gray-200 p-3">
              <div className="flex items-end gap-2">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSubmit(e as unknown as React.FormEvent);
                    }
                  }}
                  placeholder={isBusy ? "Waiting for Genie…" : "Ask about cost, usage, spend…"}
                  disabled={isBusy}
                  rows={2}
                  className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-[#FF3621] focus:outline-none focus:ring-1 focus:ring-[#FF3621] disabled:bg-gray-50"
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isBusy}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-white transition-colors disabled:cursor-not-allowed"
                  style={{ backgroundColor: !input.trim() || isBusy ? "#FFA390" : "#FF3621" }}
                >
                  {isBusy ? "…" : "Send"}
                </button>
              </div>
              <p className="mt-1.5 text-xs text-gray-400">Enter to send · Shift + Enter for newline</p>
            </form>
          </>
        )}
      </aside>
    </>
  );
}

const STARTERS = [
  "What did we spend on SQL warehouses last month?",
  "Top 5 workspaces by DBU cost, last 30 days",
  "Show me Unity Gateway usage broken down by model",
  "Which jobs cost the most in the last 7 days?",
];

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="text-sm text-gray-600">
      <p className="mb-3 font-medium text-gray-900">Ask about cost, usage, or spend across your workspaces.</p>
      <p className="mb-3">Genie will answer against your system billing tables and any assets curated in the space.</p>
      <div className="space-y-1.5">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Try one of these</p>
        {STARTERS.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onPick(q)}
            className="block w-full rounded-lg border border-gray-200 px-3 py-2 text-left text-sm text-gray-700 transition-colors hover:border-[#FF3621] hover:text-[#FF3621]"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function TurnBubble({
  turn,
  onFollowUp,
}: {
  turn: ConversationalTurn;
  onFollowUp: (q: string) => void;
}) {
  const [showSql, setShowSql] = useState(false);
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg bg-[#FF3621] px-3 py-2 text-sm text-white">{turn.text}</div>
      </div>
    );
  }

  if (turn.pending) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#FF3621] [animation-delay:0ms]" />
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#FF3621] [animation-delay:120ms]" />
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#FF3621] [animation-delay:240ms]" />
        <span>Genie is thinking…</span>
      </div>
    );
  }

  if (turn.error) {
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 ring-1 ring-inset ring-red-200">
        <p className="font-medium">Genie couldn&apos;t answer this question.</p>
        <p className="mt-1 text-xs text-red-700">{turn.error}</p>
      </div>
    );
  }

  const rows = turn.rows ?? [];
  const columns = turn.columns ?? [];
  const followUps = extractFollowUps(turn.text);

  return (
    <div className="space-y-2">
      <div className="rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-800 ring-1 ring-inset ring-gray-200">
        <p className="whitespace-pre-wrap">{turn.text || "(no answer)"}</p>
      </div>

      {turn.sql && (
        <div className="rounded-lg border border-gray-200 bg-white">
          <button
            type="button"
            onClick={() => setShowSql((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-gray-600 hover:text-gray-900"
          >
            <span>{showSql ? "Hide SQL" : "View SQL"}</span>
            <svg
              className={`h-3 w-3 transition-transform ${showSql ? "rotate-180" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {showSql && (
            <pre className="max-h-64 overflow-auto border-t border-gray-100 bg-gray-900 px-3 py-2 text-xs text-gray-100">
              <code>{turn.sql}</code>
            </pre>
          )}
        </div>
      )}

      {rows.length > 0 && columns.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50">
              <tr>
                {columns.map((c) => (
                  <th key={c} className="px-2 py-1 text-left font-medium text-gray-600">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 20).map((row, i) => (
                <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                  {(row as unknown[]).map((cell, j) => (
                    <td key={j} className="px-2 py-1 text-gray-700">{formatCell(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 20 && (
            <p className="border-t border-gray-100 px-2 py-1 text-right text-[11px] text-gray-500">
              Showing first 20 of {rows.length} rows
            </p>
          )}
        </div>
      )}

      {followUps.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {followUps.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => onFollowUp(q)}
              className="rounded-full border border-gray-200 bg-white px-2.5 py-1 text-xs text-gray-700 transition-colors hover:border-[#FF3621] hover:text-[#FF3621]"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

// Parse "Follow-up:" or bullet-list style suggestions out of the assistant text.
// Genie occasionally appends suggestions on new lines starting with "-" or "•".
function extractFollowUps(text: string): string[] {
  if (!text) return [];
  const lines = text.split(/\r?\n/);
  const followUps: string[] = [];
  let inList = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (/^(follow[- ]?ups?|next questions?|try asking)[:]/i.test(line)) {
      inList = true;
      continue;
    }
    if (inList) {
      const m = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
      if (m && m[1]) {
        followUps.push(m[1].trim());
        continue;
      }
      if (!line) continue;
      break;
    }
  }
  return followUps.slice(0, 4);
}
