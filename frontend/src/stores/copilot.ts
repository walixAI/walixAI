/**
 * C5 — Copiloto conversacional: store Zustand.
 *
 * Sin persist — el historial es privado por usuario y vive en el backend
 * (GET /api/ai/copilot/history). Solo la sesión abierta se carga en memoria.
 */
import { create } from "zustand";
import { apiRequest } from "@/lib/queries/_client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CopilotMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolsUsed: string[];   // tool_calls_made from backend
  isError: boolean;
  timestamp: number;
}

export interface CopilotEntity {
  type: string;   // "deal" | "contact" | …
  id: string;     // UUID
}

type CopilotStatus = "idle" | "thinking" | "executing";

interface HistoryRow {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls: { name?: string }[];
  created_at: string;
}

interface CopilotState {
  open: boolean;
  messages: CopilotMessage[];
  status: CopilotStatus;
  sessionId: string;
  entity: CopilotEntity | null;
  /** Sessions whose history has already been fetched from the backend. */
  loadedSessions: Set<string>;

  openDrawer: () => void;
  closeDrawer: () => void;
  /**
   * Change active session/entity context.
   * If sessionId changes, clears local messages and (re)loads history when the
   * drawer is open.
   */
  setContext: (sessionId: string, entity?: CopilotEntity | null) => void;
  loadHistoryForCurrentSession: () => Promise<void>;
  send: (text: string) => Promise<void>;
  /** Start a fresh conversation with a new session UUID. Does NOT delete the old session from the backend. */
  newConversation: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function newSessionId(): string {
  return `conv-${crypto.randomUUID()}`;
}

function rowToMessage(row: HistoryRow): CopilotMessage | null {
  // Skip "tool" role rows — they are internal plumbing, not user-visible
  if (row.role === "tool") return null;
  const toolsUsed = (row.tool_calls ?? [])
    .map((tc) => tc.name ?? "")
    .filter(Boolean);
  return {
    id: row.id,
    role: row.role as "user" | "assistant",
    content: row.content,
    toolsUsed,
    isError: false,
    timestamp: new Date(row.created_at).getTime(),
  };
}

// ── Store ─────────────────────────────────────────────────────────────────────

export const useCopilotStore = create<CopilotState>((set, get) => ({
  open: false,
  messages: [],
  status: "idle",
  sessionId: "global",
  entity: null,
  loadedSessions: new Set(),

  openDrawer: () => {
    set({ open: true });
    // Trigger history load when drawer first opens
    const { loadedSessions, sessionId } = get();
    if (!loadedSessions.has(sessionId)) {
      get().loadHistoryForCurrentSession();
    }
  },

  closeDrawer: () => set({ open: false }),

  setContext: (sessionId, entity = null) => {
    const prev = get();
    const sessionChanged = sessionId !== prev.sessionId;

    if (sessionChanged) {
      set({
        sessionId,
        entity,
        messages: [],
        status: "idle",
      });
      // Reload history for the new session if drawer is open
      if (prev.open && !get().loadedSessions.has(sessionId)) {
        get().loadHistoryForCurrentSession();
      }
    } else {
      set({ entity });
    }
  },

  loadHistoryForCurrentSession: async () => {
    const { sessionId, loadedSessions } = get();
    if (loadedSessions.has(sessionId)) return;

    try {
      const rows = await apiRequest<HistoryRow[]>(
        `/api/ai/copilot/history?session_id=${encodeURIComponent(sessionId)}`,
      );
      const messages = rows.map(rowToMessage).filter((m): m is CopilotMessage => m !== null);
      set((s) => ({
        messages,
        loadedSessions: new Set([...s.loadedSessions, sessionId]),
      }));
    } catch {
      // Non-fatal: history load failure just shows an empty conversation
    }
  },

  send: async (text: string) => {
    const { sessionId, entity } = get();

    // Optimistic: add user message immediately
    const userMsg: CopilotMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      toolsUsed: [],
      isError: false,
      timestamp: Date.now(),
    };
    set((s) => ({ messages: [...s.messages, userMsg], status: "thinking" }));

    try {
      const data = await apiRequest<{ reply: string; tool_calls_made: string[] }>(
        "/api/ai/copilot/chat",
        {
          method: "POST",
          body: JSON.stringify({
            message: text,
            session_id: sessionId,
            entity_type: entity?.type ?? null,
            entity_id: entity?.id ?? null,
          }),
        },
      );

      const assistantMsg: CopilotMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.reply,
        toolsUsed: data.tool_calls_made ?? [],
        isError: false,
        timestamp: Date.now(),
      };
      set((s) => ({
        messages: [...s.messages, assistantMsg],
        status: "idle",
      }));
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Error desconocido";
      const errMsg: CopilotMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `No pude procesar tu mensaje: ${detail}. Por favor intenta de nuevo.`,
        toolsUsed: [],
        isError: true,
        timestamp: Date.now(),
      };
      set((s) => ({ messages: [...s.messages, errMsg], status: "idle" }));
    }
  },

  newConversation: () => {
    set({
      sessionId: newSessionId(),
      messages: [],
      status: "idle",
      entity: null,
    });
    // The new sessionId is not in loadedSessions → next openDrawer will load history (which will be empty)
  },
}));
