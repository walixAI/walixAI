/**
 * Metrics query hooks — ROI and Forecast summaries.
 * Used by the Desempeño panel widgets.
 */
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "./_client";

// ── ROI ───────────────────────────────────────────────────────────────────────

export interface RoiSummary {
  period_days: number;
  period_label: string;
  leads_total: number;
  bot_qualification_rate: number;
  conversion_rate: number;
  estimated_hours_saved: number;
  estimated_revenue: number | null;
  avg_response_time_minutes: number | null;
}

export function useRoiSummary(period: 7 | 30 | 90 = 30) {
  return useQuery({
    queryKey: ["roi-summary", period],
    queryFn: () => apiRequest<RoiSummary>(`/api/metrics/roi?period=${period}`),
    staleTime: 300_000,
  });
}

// ── Forecast ──────────────────────────────────────────────────────────────────

export interface ForecastSummary {
  pipeline_forecast: { high: number; medium: number; low: number };
  high_probability_leads: unknown[];
  at_risk_leads: unknown[];
}

export function useForecastSummary() {
  return useQuery({
    queryKey: ["forecast-summary"],
    queryFn: () => apiRequest<ForecastSummary>("/api/metrics/forecast"),
    staleTime: 300_000,
  });
}
