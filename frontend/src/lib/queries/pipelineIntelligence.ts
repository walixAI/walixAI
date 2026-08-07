import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";

export interface HealthSignal {
  label: string;
  value: string;
  tone: "positive" | "negative" | "neutral";
}

export interface PipelineHealth {
  score: number;
  status: "excellent" | "good" | "warning" | "critical";
  summary: string;
  signals: HealthSignal[];
}

export interface ClosingSoonDeal {
  id: string;
  name: string;
  amount: number;
  pipeline_name: string;
  stage_name: string;
  owner_name: string | null;
  contact_id: string | null;
  expected_close_date: string | null;
}

export interface Risk {
  title: string;
  severity: "high" | "medium" | "low";
  detail: string;
}

export interface PipelineIntelligence {
  generated_at: string;
  pipeline_health: PipelineHealth;
  closing_soon: ClosingSoonDeal[];
  risks: Risk[];
  executive_summary: string;
  source: "live" | "fallback";
}

async function fetchIntelligence(forceRefresh = false): Promise<PipelineIntelligence> {
  const params = forceRefresh ? "?force_refresh=true" : "";
  return apiRequest<PipelineIntelligence>(`/api/metrics/pipeline-intelligence${params}`);
}

export function usePipelineIntelligence() {
  return useQuery({
    queryKey: ["pipeline-intelligence"],
    queryFn: () => fetchIntelligence(false),
    staleTime: 60_000,
  });
}

export function useRefreshIntelligence() {
  const qc = useQueryClient();
  return async () => {
    const fresh = await fetchIntelligence(true);
    qc.setQueryData(["pipeline-intelligence"], fresh);
    return fresh;
  };
}
