import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "./_client";

export interface FunnelStage {
  stage_name: string;
  stage_order: number;
  deals_reached: number;
  conversion_from_prev: number | null;
}

export interface LeadSource {
  source: string;
  count: number;
  revenue: number;
}

export interface LostReason {
  reason: string;
  count: number;
  lost_amount: number;
}

export interface ActivityHeatmapCell {
  user_id: string;
  user_name: string;
  day: string;
  whatsapp_count: number;
  activity_count: number;
  deals_moved_count: number;
}

export interface ReportsExtra {
  period_days: number;
  funnel: FunnelStage[];
  lead_sources: LeadSource[];
  lost_reasons: LostReason[];
  activity_heatmap: ActivityHeatmapCell[];
}

export function useReportsExtra(period = 30, branchId?: string) {
  return useQuery({
    queryKey: ["reports-extra", period, branchId ?? null],
    queryFn: () => {
      const params = new URLSearchParams({ period: String(period) });
      if (branchId) params.set("branch_id", branchId);
      return apiRequest<ReportsExtra>(`/api/metrics/desempeno-extra?${params}`);
    },
    staleTime: 300_000,
  });
}
