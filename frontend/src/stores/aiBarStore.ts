import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

// suggested_actions are plain strings matching the backend shape.
// Display logic (navigate / confirm / send) lives in AIPanel.

export interface AIBarMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  suggested_actions?: string[];
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

  setOpen: (v: boolean) => void;
  setMinimized: (v: boolean) => void;
  addMessage: (
    role: AIBarMessage["role"],
    content: string,
    suggested_actions?: string[],
  ) => void;
  setContext: (ctx: Partial<AIBarContext>) => void;
  setLoading: (v: boolean) => void;
  setDraftInput: (v: string) => void;
  setPendingSuggestionsCount: (n: number) => void;
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

      setOpen: (isOpen) => set({ isOpen }),
      setMinimized: (isMinimized) => set({ isMinimized }),
      addMessage: (role, content, suggested_actions) =>
        set((s) => ({
          history: [
            ...s.history,
            { role, content, timestamp: Date.now(), suggested_actions },
          ],
        })),
      setContext: (ctx) =>
        set((s) => ({ currentContext: { ...s.currentContext, ...ctx } })),
      setLoading: (isLoading) => set({ isLoading }),
      setDraftInput: (draftInput) => set({ draftInput }),
      setPendingSuggestionsCount: (pendingSuggestionsCount) => set({ pendingSuggestionsCount }),
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
