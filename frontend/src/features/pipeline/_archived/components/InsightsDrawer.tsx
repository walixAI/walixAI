import { useState } from "react";
import { Sparkles, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  api,
  type PipelineInsightsOut,
  type PipelineInsightRisk,
  type PipelineInsightRecommendation,
} from "@/lib/api";
import { useOpportunityStore } from "../opportunityStore";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

type DrawerState = "idle" | "loading" | "result";

const SEVERITY_STYLE: Record<string, string> = {
  high: "border-l-danger text-danger bg-danger/5",
  medium: "border-l-warning text-warning bg-warning/5",
  low: "border-l-muted-foreground text-muted-foreground bg-muted",
};
const SEVERITY_LABEL: Record<string, string> = {
  high: "Alto",
  medium: "Medio",
  low: "Bajo",
};
const IMPACT_STYLE: Record<string, string> = {
  high: "bg-success/10 text-success border border-success/20",
  medium: "bg-warning/10 text-warning border border-warning/20",
  low: "bg-muted text-muted-foreground border border-border",
};
const IMPACT_LABEL: Record<string, string> = {
  high: "Alto impacto",
  medium: "Impacto medio",
  low: "Bajo impacto",
};

function HealthBar({ score }: { score: number }) {
  const colorClass =
    score >= 70 ? "bg-success" : score >= 40 ? "bg-warning" : "bg-danger";
  const textClass =
    score >= 70 ? "text-success" : score >= 40 ? "text-warning" : "text-danger";
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <span className={cn("text-5xl font-black tabular-nums", textClass)}>{score}</span>
        <span className="text-lg text-muted-foreground font-medium">/ 100</span>
      </div>
      <div className="h-2.5 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-700", colorClass)}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

function RiskCard({ risk }: { risk: PipelineInsightRisk }) {
  const styleClass = SEVERITY_STYLE[risk.severity] ?? SEVERITY_STYLE.low;
  return (
    <div className={cn("rounded-lg border-l-4 p-3 space-y-1", styleClass)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold leading-snug">{risk.title}</p>
        <span
          className={cn(
            "text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0",
            {
              "bg-danger/10 text-danger border border-danger/20": risk.severity === "high",
              "bg-warning/10 text-warning border border-warning/20": risk.severity === "medium",
              "bg-muted text-muted-foreground border border-border": risk.severity === "low",
            },
          )}
        >
          {SEVERITY_LABEL[risk.severity] ?? risk.severity}
        </span>
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">{risk.description}</p>
    </div>
  );
}

function RecCard({ rec }: { rec: PipelineInsightRecommendation }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold leading-snug">{rec.title}</p>
        <span
          className={cn(
            "text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0",
            IMPACT_STYLE[rec.impact] ?? IMPACT_STYLE.low,
          )}
        >
          {IMPACT_LABEL[rec.impact] ?? rec.impact}
        </span>
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">{rec.action}</p>
    </div>
  );
}

export function InsightsDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { branchId, fetchBoard } = useOpportunityStore();
  const [state, setState] = useState<DrawerState>("idle");
  const [insights, setInsights] = useState<PipelineInsightsOut | null>(null);
  const [bulkLoading, setBulkLoading] = useState(false);

  async function handleAnalyze() {
    if (!branchId) {
      toast.info("La IA no está disponible ahora");
      return;
    }
    setState("loading");
    try {
      const data = await api.getPipelineInsights(branchId);
      setInsights(data);
      setState("result");
    } catch {
      toast.info("La IA no está disponible ahora");
      setState("idle");
    }
  }

  async function handleBulkSuggestions() {
    if (!branchId) return;
    setBulkLoading(true);
    try {
      await api.triggerBulkSuggestions(branchId);
      toast.success("Sugerencias generándose en segundo plano");
      // Refresh board after a short delay to show new chips
      setTimeout(() => fetchBoard(branchId), 3000);
    } catch {
      toast.info("La IA no está disponible ahora");
    } finally {
      setBulkLoading(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-[460px] flex flex-col p-0 gap-0 overflow-hidden"
      >
        <SheetHeader className="px-6 pt-6 pb-4 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" aria-hidden="true" />
            <SheetTitle className="text-base font-bold">Insights IA</SheetTitle>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          {state === "idle" && (
            <div className="flex flex-col items-center justify-center h-full min-h-[300px] gap-4">
              <div className="rounded-2xl border-2 border-dashed border-border p-8 flex flex-col items-center gap-4 text-center max-w-[280px]">
                <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center">
                  <Sparkles className="h-6 w-6 text-primary" aria-hidden="true" />
                </div>
                <div className="space-y-1.5">
                  <p className="font-semibold text-base">Analizar Pipeline</p>
                  <p className="text-sm text-muted-foreground">
                    Obtén insights sobre el estado de tu pipeline de oportunidades.
                  </p>
                </div>
                <Button onClick={handleAnalyze} className="w-full gap-2">
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                  Analizar ahora
                </Button>
              </div>
            </div>
          )}

          {state === "loading" && (
            <div
              className="space-y-4"
              aria-busy="true"
              aria-label="Analizando pipeline"
            >
              <Skeleton className="h-24 w-full rounded-xl" />
              <Skeleton className="h-20 w-full rounded-xl" />
              <Skeleton className="h-20 w-full rounded-xl" />
              <p className="text-xs text-muted-foreground text-center">
                Analizando tu pipeline…
              </p>
            </div>
          )}

          {state === "result" && insights && (
            <div className="space-y-6">
              {/* Health score */}
              <div className="space-y-3">
                <HealthBar score={insights.health_score} />
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {insights.summary}
                </p>
              </div>

              {/* Risks */}
              {insights.risks.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-bold text-muted-foreground uppercase tracking-wide">
                    Riesgos
                  </p>
                  {insights.risks.map((r, i) => (
                    <RiskCard key={i} risk={r} />
                  ))}
                </div>
              )}

              {/* Recommendations */}
              {insights.recommendations.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-bold text-muted-foreground uppercase tracking-wide">
                    Recomendaciones
                  </p>
                  {insights.recommendations.map((r, i) => (
                    <RecCard key={i} rec={r} />
                  ))}
                </div>
              )}

              {/* Bulk suggestions card */}
              <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
                  <p className="text-sm font-semibold">Sugerencias por oportunidad</p>
                </div>
                <p className="text-xs text-muted-foreground">
                  Genera una sugerencia de próximo paso para cada oportunidad abierta.
                  Se procesa en segundo plano.
                </p>
                <Button
                  onClick={handleBulkSuggestions}
                  disabled={bulkLoading}
                  className="w-full gap-2"
                >
                  {bulkLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Sparkles className="h-4 w-4" aria-hidden="true" />
                  )}
                  {bulkLoading ? "Generando…" : "Generar sugerencias ✨"}
                </Button>
              </div>
            </div>
          )}
        </div>

        {state === "result" && (
          <div className="px-6 pb-6 shrink-0 border-t border-border pt-4">
            <Button
              variant="outline"
              className="w-full gap-2"
              onClick={handleAnalyze}
              disabled={state === "loading"}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Re-analizar
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
