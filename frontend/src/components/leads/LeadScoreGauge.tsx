import { useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer,
  LineChart, Line, ResponsiveContainer as RC2,
} from "recharts";
import { CheckCircle2, XCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface LeadScoreGaugeProps {
  leadId: string;
}

function gaugeFill(score: number): string {
  if (score >= 70) return "hsl(var(--success))";
  if (score >= 40) return "hsl(var(--warning))";
  return "hsl(var(--danger))";
}

export function LeadScoreGauge({ leadId }: LeadScoreGaugeProps) {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["lead-score", leadId],
    queryFn: () => api.getLeadScore(leadId),
    enabled: Boolean(leadId),
    staleTime: 60_000,
  });

  const recalc = useMutation({
    mutationFn: () => api.recalculateLeadScore(leadId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead-score", leadId] });
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
      qc.invalidateQueries({ queryKey: ["pipeline-board"] });
      toast.success("Score recalculado");
    },
    onError: (e: Error) => toast.error("Error al recalcular", { description: e.message }),
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-[140px] w-full rounded-xl" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    );
  }

  const score = data?.current_score ?? 0;
  const trend = data?.current_score_trend;
  const latest = data?.history[0] ?? null;
  const positiveFactors = latest?.positive_factors?.items ?? [];
  const negativeFactors = latest?.negative_factors?.items ?? [];
  const historyData = (data?.history ?? []).slice().reverse().map((h, i) => ({
    i,
    score: h.score,
  }));

  const fill = gaugeFill(score);
  const chartData = [{ value: score }];

  return (
    <div className="space-y-4">
      {/* Radial gauge + sparkline row */}
      <div className="flex items-center gap-4">
        {/* Gauge */}
        <div className="relative h-[120px] w-[120px] shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <RadialBarChart
              innerRadius={42}
              outerRadius={56}
              startAngle={90}
              endAngle={-270}
              data={chartData}
              barSize={10}
            >
              <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
              <RadialBar
                background={{ fill: "hsl(var(--muted))" }}
                dataKey="value"
                angleAxisId={0}
                cornerRadius={5}
                fill={fill}
              />
            </RadialBarChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <div className="font-syne text-xl font-bold leading-none" style={{ color: fill }}>
                {score}
              </div>
              <div className="text-[9px] text-muted-foreground">/ 100</div>
            </div>
          </div>
        </div>

        {/* Sparkline + trend */}
        <div className="flex-1 min-w-0">
          {historyData.length >= 2 ? (
            <RC2 width="100%" height={50}>
              <LineChart data={historyData}>
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke={fill}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </RC2>
          ) : (
            <div className="h-[50px] flex items-center">
              <p className="text-xs text-muted-foreground">Sin historial suficiente</p>
            </div>
          )}
          <div className="flex items-center gap-1.5 mt-1">
            <span className="text-xs text-muted-foreground">Tendencia:</span>
            <span className={`text-xs font-semibold ${trend === "up" ? "text-success" : trend === "down" ? "text-danger" : "text-muted-foreground"}`}>
              {trend === "up" ? "↑ Subiendo" : trend === "down" ? "↓ Bajando" : "→ Estable"}
            </span>
          </div>
        </div>
      </div>

      {/* Factors */}
      {(positiveFactors.length > 0 || negativeFactors.length > 0) && (
        <div className="space-y-2">
          {positiveFactors.length > 0 && (
            <div className="space-y-1">
              {positiveFactors.map((f, i) => (
                <div key={i} className="flex items-start gap-1.5 text-xs">
                  <CheckCircle2 className="h-3 w-3 text-success shrink-0 mt-0.5" />
                  <span className="text-foreground/80">{f}</span>
                </div>
              ))}
            </div>
          )}
          {negativeFactors.length > 0 && (
            <div className="space-y-1">
              {negativeFactors.map((f, i) => (
                <div key={i} className="flex items-start gap-1.5 text-xs">
                  <XCircle className="h-3 w-3 text-danger shrink-0 mt-0.5" />
                  <span className="text-foreground/80">{f}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Recalculate */}
      <Button
        variant="outline"
        size="sm"
        className="w-full gap-2 h-8 text-xs"
        onClick={() => recalc.mutate()}
        disabled={recalc.isPending}
      >
        <RefreshCw className={`h-3 w-3 ${recalc.isPending ? "animate-spin" : ""}`} />
        {recalc.isPending ? "Calculando…" : "Recalcular"}
      </Button>
    </div>
  );
}
