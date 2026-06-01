import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export interface AIBarAction {
  type: string;
  label: string;
  payload?: Record<string, unknown>;
}

export interface AIBarMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  suggested_actions?: AIBarAction[];
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

  setOpen: (v: boolean) => void;
  setMinimized: (v: boolean) => void;
  addMessage: (
    role: AIBarMessage["role"],
    content: string,
    suggested_actions?: AIBarAction[],
  ) => void;
  setContext: (ctx: Partial<AIBarContext>) => void;
  setLoading: (v: boolean) => void;
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
