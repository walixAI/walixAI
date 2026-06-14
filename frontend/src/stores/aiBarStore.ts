import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { AIActionData } from "@/lib/api";

// suggested_actions are plain strings matching the backend shape.
// Display logic (navigate / confirm / send) lives in AIPanel.

export interface AIBarMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  suggested_actions?: string[];
  action_data?: AIActionData | null;
}

export interface AIBarContext {
  screen?: string;
  branch_id?: string;
  lead_id?: string;
  [key: string]: unknown;
}

interface AIBarState {
  isOpen: boolean;
  isMinimized: boolean;
  history: AIBarMessage[];
  currentContext: AIBarContext;
  isLoading: boolean;
  /** Text pre-filled into the bar input by a suggested-action chip click. */
  draftInput: string;
  /** Count of pending agent suggestions for the current user. */
  pendingSuggestionsCount: number;
  /** Programmatic command queued by AIPanel (e.g. delete confirmation). */
  pendingCommand: {
    message: string;
    displayText?: string;
    context?: Record<string, unknown>;
  } | null;

  setOpen: (v: boolean) => void;
  setMinimized: (v: boolean) => void;
  addMessage: (
    role: AIBarMessage["role"],
    content: string,
    suggested_actions?: string[],
    action_data?: AIActionData | null,
  ) => void;
  setContext: (ctx: Partial<AIBarContext>) => void;
  setLoading: (v: boolean) => void;
  setDraftInput: (v: string) => void;
  setPendingSuggestionsCount: (n: number) => void;
  setPendingCommand: (cmd: AIBarState["pendingCommand"]) => void;
  clear: () => void;
}

export const useAIBarStore = create<AIBarState>()(
  persist(
    (set) => ({
      isOpen: false,
      isMinimized: false,
      history: [],
      currentContext: {},
      isLoading: false,
      draftInput: "",
      pendingSuggestionsCount: 0,
      pendingCommand: null,

      setOpen: (isOpen) => set({ isOpen }),
      setMinimized: (isMinimized) => set({ isMinimized }),
      addMessage: (role, content, suggested_actions, action_data) =>
        set((s) => ({
          history: [
            ...s.history,
            { role, content, timestamp: Date.now(), suggested_actions, action_data },
          ],
        })),
      setContext: (ctx) =>
        set((s) => ({ currentContext: { ...s.currentContext, ...ctx } })),
      setLoading: (isLoading) => set({ isLoading }),
      setDraftInput: (draftInput) => set({ draftInput }),
      setPendingSuggestionsCount: (pendingSuggestionsCount) => set({ pendingSuggestionsCount }),
      setPendingCommand: (pendingCommand) => set({ pendingCommand }),
      clear: () => set({ history: [], isOpen: false }),
    }),
    {
      name: "walix-ai-bar",
      storage: createJSONStorage(() => localStorage),
      // Only persist the minimized preference; conversation is session-only
      partialize: (s) => ({ isMinimized: s.isMinimized }),
    },
  ),
);
