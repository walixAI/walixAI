import { create } from "zustand";
import type {
  OppBoardStage,
  OppCard,
  OppForecastRead,
  OppStaleRead,
  OppRead,
  OppDetailRead,
} from "@/lib/api";
import { api } from "@/lib/api";

export interface OppFilters {
  search: string;
  assignedTo: string | null;
  minAmount: number | null;
  maxAmount: number | null;
  closeDateBefore: string | null;
  source: string | null;
}

/** Convert a full OppRead (from mutation responses) into the lighter OppCard shape used by the board. */
export function oppReadToCard(opp: OppRead): OppCard {
  return {
    id: opp.id,
    title: opp.title,
    amount: opp.amount,
    currency: opp.currency,
    probability: opp.probability,
    close_date: opp.close_date,
    status: opp.status,
    stage_entered_at: opp.stage_entered_at,
    last_activity_at: opp.last_activity_at,
    ai_suggestion: opp.ai_suggestion,
    ai_suggestion_urgency: opp.ai_suggestion_urgency,
    urgency_score: opp.urgency_score,
    assigned_to: opp.assigned_to,
    assigned_to_name: opp.assigned_to_name,
    lead_name: opp.lead?.name ?? null,
    lead_wa_phone: opp.lead?.wa_phone ?? null,
    days_in_stage: opp.days_in_stage,
  };
}

interface OpportunityState {
  // ── Board ────────────────────────────────────────────────────────────────────
  stages: OppBoardStage[];
  boardByStage: Record<string, OppCard[]>;
  currency: string;

  // ── Side data ────────────────────────────────────────────────────────────────
  forecast: OppForecastRead | null;
  stale: OppStaleRead | null;

  // ── UI ───────────────────────────────────────────────────────────────────────
  filters: OppFilters;
  selectedIds: Set<string>;
  view: "kanban" | "list";
  loading: boolean;
  forecastLoading: boolean;
  staleLoading: boolean;
  branchId: string | null;
  error: string | null;

  // ── Drawer ───────────────────────────────────────────────────────────────────
  drawerOpen: boolean;
  drawerOppId: string | null;
  drawerOpp: OppDetailRead | null;
  drawerLoading: boolean;

  // ── Modals ───────────────────────────────────────────────────────────────────
  newOppModalOpen: boolean;
  newOppStageId: string | null;
  lostModalOppId: string | null;
  taskModalOppId: string | null;

  // ── Board actions ────────────────────────────────────────────────────────────
  fetchBoard: (branchId?: string) => Promise<void>;
  fetchForecast: (branchId?: string) => Promise<void>;
  fetchStale: (branchId?: string) => Promise<void>;
  fetchAll: (branchId?: string) => Promise<void>;
  optimisticMove: (oppId: string, toStageId: string) => () => void;
  addCardToStage: (card: OppCard, stageId: string) => void;
  refreshBoardCard: (opp: OppRead) => void;
  removeCard: (oppId: string) => void;

  // ── Filters ──────────────────────────────────────────────────────────────────
  setFilter: <K extends keyof OppFilters>(key: K, value: OppFilters[K]) => void;
  resetFilters: () => void;

  // ── Selection ────────────────────────────────────────────────────────────────
  toggleSelect: (id: string) => void;
  clearSelection: () => void;

  // ── View ─────────────────────────────────────────────────────────────────────
  setView: (view: "kanban" | "list") => void;

  // ── Drawer actions ───────────────────────────────────────────────────────────
  openDrawer: (oppId: string) => void;
  closeDrawer: () => void;
  fetchDrawerOpp: (id: string) => Promise<void>;

  // ── Modal actions ────────────────────────────────────────────────────────────
  openNewOppModal: (stageId?: string) => void;
  closeNewOppModal: () => void;
  openLostModal: (oppId: string) => void;
  closeLostModal: () => void;
  openTaskModal: (oppId: string) => void;
  closeTaskModal: () => void;
}

const DEFAULT_FILTERS: OppFilters = {
  search: "",
  assignedTo: null,
  minAmount: null,
  maxAmount: null,
  closeDateBefore: null,
  source: null,
};

export const useOpportunityStore = create<OpportunityState>()((set, get) => ({
  stages: [],
  boardByStage: {},
  currency: "MXN",
  forecast: null,
  stale: null,
  filters: DEFAULT_FILTERS,
  selectedIds: new Set<string>(),
  view: "kanban",
  loading: false,
  forecastLoading: false,
  staleLoading: false,
  branchId: null,
  error: null,

  drawerOpen: false,
  drawerOppId: null,
  drawerOpp: null,
  drawerLoading: false,

  newOppModalOpen: false,
  newOppStageId: null,
  lostModalOppId: null,
  taskModalOppId: null,

  // ── Board ────────────────────────────────────────────────────────────────────

  fetchBoard: async (branchId?: string) => {
    set({ loading: true, error: null, branchId: branchId ?? null });
    try {
      const data = await api.getOpportunityBoard(branchId);
      const boardByStage: Record<string, OppCard[]> = {};
      for (const stage of data.stages) {
        boardByStage[stage.id] = stage.opportunities;
      }
      set({ stages: data.stages, boardByStage, currency: data.currency, loading: false });
    } catch (e) {
      set({
        loading: false,
        error: e instanceof Error ? e.message : "Error al cargar el tablero",
      });
    }
  },

  fetchForecast: async (branchId?: string) => {
    set({ forecastLoading: true });
    try {
      const data = await api.getOpportunityForecast(branchId);
      set({ forecast: data, forecastLoading: false });
    } catch {
      set({ forecastLoading: false });
    }
  },

  fetchStale: async (branchId?: string) => {
    set({ staleLoading: true });
    try {
      const data = await api.getStaleOpportunities(branchId);
      set({ stale: data, staleLoading: false });
    } catch {
      set({ staleLoading: false });
    }
  },

  fetchAll: async (branchId?: string) => {
    const { fetchBoard, fetchForecast, fetchStale } = get();
    await Promise.all([fetchBoard(branchId), fetchForecast(branchId), fetchStale(branchId)]);
  },

  optimisticMove: (oppId, toStageId) => {
    const current = get().boardByStage;
    const snapshot: Record<string, OppCard[]> = {};
    for (const [k, v] of Object.entries(current)) snapshot[k] = [...v];

    let movedCard: OppCard | null = null;
    let fromStageId: string | null = null;
    for (const [stageId, cards] of Object.entries(current)) {
      const card = cards.find((c) => c.id === oppId);
      if (card) { movedCard = card; fromStageId = stageId; break; }
    }
    if (!movedCard || !fromStageId || fromStageId === toStageId) return () => {};

    const updated = { ...current };
    updated[fromStageId] = current[fromStageId].filter((c) => c.id !== oppId);
    updated[toStageId] = [...(current[toStageId] ?? []), movedCard];
    set({ boardByStage: updated });
    return () => set({ boardByStage: snapshot });
  },

  addCardToStage: (card, stageId) =>
    set((s) => ({
      boardByStage: {
        ...s.boardByStage,
        [stageId]: [...(s.boardByStage[stageId] ?? []), card],
      },
    })),

  refreshBoardCard: (opp) =>
    set((s) => {
      const updated = { ...s.boardByStage };
      for (const [stageId, cards] of Object.entries(updated)) {
        const idx = cards.findIndex((c) => c.id === opp.id);
        if (idx >= 0) {
          const newCards = [...cards];
          newCards[idx] = oppReadToCard(opp);
          updated[stageId] = newCards;
          break;
        }
      }
      // If stage changed, move the card
      if (opp.stage?.id) {
        const newStageId = opp.stage.id;
        const currentStageId = Object.keys(s.boardByStage).find((sid) =>
          s.boardByStage[sid].some((c) => c.id === opp.id),
        );
        if (currentStageId && currentStageId !== newStageId) {
          updated[currentStageId] = (updated[currentStageId] ?? []).filter(
            (c) => c.id !== opp.id,
          );
          updated[newStageId] = [...(updated[newStageId] ?? []), oppReadToCard(opp)];
        }
      }
      return { boardByStage: updated };
    }),

  removeCard: (oppId) =>
    set((s) => {
      const updated = { ...s.boardByStage };
      for (const [stageId, cards] of Object.entries(updated)) {
        if (cards.some((c) => c.id === oppId)) {
          updated[stageId] = cards.filter((c) => c.id !== oppId);
          break;
        }
      }
      return { boardByStage: updated };
    }),

  // ── Filters ──────────────────────────────────────────────────────────────────

  setFilter: (key, value) => set((s) => ({ filters: { ...s.filters, [key]: value } })),
  resetFilters: () => set({ filters: DEFAULT_FILTERS }),

  // ── Selection ────────────────────────────────────────────────────────────────

  toggleSelect: (id) =>
    set((s) => {
      const next = new Set(s.selectedIds);
      if (next.has(id)) next.delete(id); else next.add(id);
      return { selectedIds: next };
    }),
  clearSelection: () => set({ selectedIds: new Set<string>() }),

  // ── View ─────────────────────────────────────────────────────────────────────

  setView: (view) => set({ view }),

  // ── Drawer ───────────────────────────────────────────────────────────────────

  openDrawer: (oppId) => {
    set({ drawerOpen: true, drawerOppId: oppId, drawerOpp: null });
    get().fetchDrawerOpp(oppId);
  },

  closeDrawer: () => set({ drawerOpen: false, drawerOppId: null, drawerOpp: null }),

  fetchDrawerOpp: async (id) => {
    set({ drawerLoading: true });
    try {
      const data = await api.getOpportunity(id);
      set({ drawerOpp: data, drawerLoading: false });
    } catch {
      set({ drawerLoading: false });
    }
  },

  // ── Modals ───────────────────────────────────────────────────────────────────

  openNewOppModal: (stageId) => set({ newOppModalOpen: true, newOppStageId: stageId ?? null }),
  closeNewOppModal: () => set({ newOppModalOpen: false, newOppStageId: null }),
  openLostModal: (oppId) => set({ lostModalOppId: oppId }),
  closeLostModal: () => set({ lostModalOppId: null }),
  openTaskModal: (oppId) => set({ taskModalOppId: oppId }),
  closeTaskModal: () => set({ taskModalOppId: null }),
}));
