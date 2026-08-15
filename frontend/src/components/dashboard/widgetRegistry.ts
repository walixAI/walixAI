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
import { SalesFunnelChart } from "./SalesFunnelChart";
import { LeadSourcesChart } from "./LeadSourcesChart";
import { LostDealsChart } from "./LostDealsChart";
import { TeamActivityHeatmap } from "./TeamActivityHeatmap";
import { AiIntelligenceSection } from "./AiIntelligenceSection";

export const widgetRegistry: Record<string, ComponentType> = {
  // Panel: principal — el orden real de aparición NO se define acá, sino
  // por DashboardWidget.default_position en el catálogo (backend), resuelto
  // en cascada con dashboard_layouts vía _resolve_layout(). Este mapa es
  // solo key -> componente; el agrupamiento por comentario es documentación,
  // no código, así que confirmar contra el catálogo real (surface) antes de
  // asumir a qué panel pertenece un widget.
  kpi_cards:                   KpiCardsRow,
  run_rate_profitability:      RunRateProfitabilityRow,
  task_cards:                  TaskCards,
  recent_activity:             RecentActivityCard,
  proactive_briefing:          ProactiveBriefing,
  ai_patterns:                 AIPatternsCard,
  pipeline_by_stage_chart:     PipelineByStageChart,
  deals_closed_timeline_chart: DealsClosedTimelineChart,
  // ai_intelligence_section vive acá — surface="principal" en la migración
  // i4j5k6l7m8n9 (confirmado contra la DB real), no en Desempeño. Un
  // comentario previo lo agrupaba mal bajo "Panel: desempeno"; era ruido
  // desactualizado, no una instrucción real — no volver a moverlo sin
  // verificar primero contra /api/dashboard/layout.
  ai_intelligence_section:     AiIntelligenceSection,
  // Panel: desempeno
  team_performance_summary:    TeamPerformanceSummary,
  ai_roi_summary:              AiRoiSummary,
  lead_quality_forecast:       LeadQualityForecastSummary,
  sales_funnel_chart:          SalesFunnelChart,
  lead_sources_chart:          LeadSourcesChart,
  lost_deals_chart:            LostDealsChart,
  team_activity_heatmap:       TeamActivityHeatmap,
};
