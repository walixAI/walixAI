/**
 * Dashboard module — API query functions.
 *
 * Mirrors the contacts.ts pattern: backend returns snake_case JSON; this module
 * exposes camelCase TypeScript interfaces and maps the response before returning.
 *
 * Endpoints (Sprint 13B):
 *   GET /api/dashboard/kpis
 *   GET /api/dashboard/activity?limit=
 *   GET /api/dashboard/pipeline-by-stage
 *   GET /api/dashboard/deals-closed-timeline?days=
 */
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "./_client";

// ── KPIs ──────────────────────────────────────────────────────────────────────
export interface KpiBundle {
  pipelineValue: number;
  pipelineDeltaPct: number;
  activeDeals: number;
  staleDeals: number;
  messagesToday: number;
  messagesUnanswered: number;
  closeRate: number;
  closeRateDelta: number;
}

export function useDashboardKpis() {
  return useQuery({
    queryKey: ["dashboard-kpis"],
    queryFn: async (): Promise<KpiBundle> => {
      const r = await apiRequest<any>("/api/dashboard/kpis");
      return {
        pipelineValue: Number(r.pipeline_value ?? 0),
        pipelineDeltaPct: Number(r.pipeline_delta_pct ?? 0),
        activeDeals: Number(r.active_deals ?? 0),
        staleDeals: Number(r.stale_deals ?? 0),
        messagesToday: Number(r.messages_today ?? 0),
        messagesUnanswered: Number(r.messages_unanswered ?? 0),
        closeRate: Number(r.close_rate ?? 0),
        closeRateDelta: Number(r.close_rate_delta ?? 0),
      };
    },
  });
}

// ── Actividad reciente ──────────────────────────────────────────────────────────
export interface RecentActivityRow {
  id: string;
  type: string;
  description: string;
  occurredAt: string;
  contactId: string | null;
  contactName: string | null;
}

export function useRecentActivity(limit = 10) {
  return useQuery({
    queryKey: ["recent-activity", limit],
    queryFn: async (): Promise<RecentActivityRow[]> => {
      const rows = await apiRequest<any[]>(`/api/dashboard/activity?limit=${limit}`);
      return (rows ?? []).map((a) => ({
        id: String(a.id),
        type: a.type,
        description: a.description,
        occurredAt: a.occurred_at,
        contactId: a.contact_id ?? null,
        contactName: a.contact_name ?? null,
      }));
    },
  });
}

// ── Pipeline por etapa ──────────────────────────────────────────────────────────
export function usePipelineByStage() {
  return useQuery({
    queryKey: ["pipeline-by-stage"],
    queryFn: async (): Promise<{ stage: string; value: number }[]> => {
      const rows = await apiRequest<any[]>("/api/dashboard/pipeline-by-stage");
      return (rows ?? []).map((s) => ({
        stage: s.stage,
        value: Number(s.value ?? 0),
      }));
    },
  });
}

// ── Oportunidades cerradas (timeline) ─────────────────────────────────────────────
export function useDealsClosedTimeline(days = 30) {
  return useQuery({
    queryKey: ["deals-closed-timeline", days],
    queryFn: async (): Promise<{ day: string; date: string; value: number }[]> => {
      const rows = await apiRequest<any[]>(
        `/api/dashboard/deals-closed-timeline?days=${days}`,
      );
      return (rows ?? []).map((d) => ({
        day: String(d.day),
        date: d.date,
        value: Number(d.value ?? 0),
      }));
    },
  });
}

// NOTA fase 2 (IA): useDashboardAiSuggestions y usePipelineHealthScore se omiten
// a propósito. Se reintroducirán al portar DashboardAiSection contra agent_suggestions.
