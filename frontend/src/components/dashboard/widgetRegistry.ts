import type { ComponentType } from "react";
import { KpiCardsRow } from "./KpiCardsRow";
import { RunRateProfitabilityRow } from "./RunRateProfitabilityRow";
import { TaskCards } from "./TaskCards";
import { RecentActivityCard } from "./RecentActivityCard";
import { ProactiveBriefing } from "@/components/walix/ProactiveBriefing";
import { AIPatternsCard } from "@/components/walix/AIPatternsCard";
import { PipelineByStageChart } from "./PipelineByStageChart";
import { DealsClosedTimelineChart } from "./DealsClosedTimelineChart";
import { TeamPerformanceSummary } from "./TeamPerformanceSummary";
import { AiRoiSummary } from "./AiRoiSummary";
import { LeadQualityForecastSummary } from "./LeadQualityForecastSummary";

export const widgetRegistry: Record<string, ComponentType> = {
  // Panel: principal
  kpi_cards:                   KpiCardsRow,
  run_rate_profitability:      RunRateProfitabilityRow,
  task_cards:                  TaskCards,
  recent_activity:             RecentActivityCard,
  proactive_briefing:          ProactiveBriefing,
  ai_patterns:                 AIPatternsCard,
  pipeline_by_stage_chart:     PipelineByStageChart,
  deals_closed_timeline_chart: DealsClosedTimelineChart,
  // Panel: desempeno
  team_performance_summary:    TeamPerformanceSummary,
  ai_roi_summary:              AiRoiSummary,
  lead_quality_forecast:       LeadQualityForecastSummary,
};
