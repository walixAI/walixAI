import type { ComponentType } from "react";
import { KpiCardsRow } from "./KpiCardsRow";
import { RunRateProfitabilityRow } from "./RunRateProfitabilityRow";
import { TaskCards } from "./TaskCards";
import { RecentActivityCard } from "./RecentActivityCard";
import { ProactiveBriefing } from "@/components/walix/ProactiveBriefing";
import { AIPatternsCard } from "@/components/walix/AIPatternsCard";
import { PipelineByStageChart } from "./PipelineByStageChart";
import { DealsClosedTimelineChart } from "./DealsClosedTimelineChart";

export const widgetRegistry: Record<string, ComponentType> = {
  kpi_cards:                   KpiCardsRow,
  run_rate_profitability:      RunRateProfitabilityRow,
  task_cards:                  TaskCards,
  recent_activity:             RecentActivityCard,
  proactive_briefing:          ProactiveBriefing,
  ai_patterns:                 AIPatternsCard,
  pipeline_by_stage_chart:     PipelineByStageChart,
  deals_closed_timeline_chart: DealsClosedTimelineChart,
};
