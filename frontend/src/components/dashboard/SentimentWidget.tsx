import { useQuery } from "@tanstack/react-query";
import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from "recharts";
import { api } from "@/lib/api";

interface SentimentWidgetProps {
  branchId?: string | null;
}

const SENTIMENT_LABELS: Record<string, { label: string; color: string }> = {
  interesado: { label: "Interesado", color: "bg-success/15 text-success border-success/20" },
  urgente:    { label: "Urgente",    color: "bg-warning/15 text-warning border-warning/20" },
  neutral:    { label: "Neutral",    color: "bg-muted text-muted-foreground border-border" },
  negativo:   { label: "Negativo",   color: "bg-danger/15 text-danger border-danger/20" },
};

function scoreColor(score: number): string {
  if (score >= 75) return "hsl(var(--success))";
  if (score >= 50) return "hsl(var(--warning))";
  return "hsl(var(--danger))";
}

export function SentimentWidget({ branchId }: SentimentWidgetProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["sentiment", branchId],
    queryFn: () => api.getSentiment({ branch_id: branchId ?? undefined }),
    enabled: !!branchId,
    staleTime: 120_000,
  });

  const current = data?.current ?? null;
  const score = current ? Math.round(current.overall_score * 100) : 0;
  const chartData = [{ value: score }];
  const fill = scoreColor(score);

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-4">Sentimiento</p>

      {isLoading ? (
        <div className="h-[160px] flex items-center justify-center">
          <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        </div>
      ) : !current ? (
        <div className="h-[160px] flex items-center justify-center text-sm text-muted-foreground">
          Sin datos de sentimiento aún
        </div>
      ) : (
        <>
          {/* Radial gauge */}
          <div className="relative h-[160px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                innerRadius={52}
                outerRadius={72}
                startAngle={90}
                endAngle={-270}
                data={chartData}
                barSize={14}
              >
                <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
                <RadialBar
                  background={{ fill: "hsl(var(--muted))" }}
                  dataKey="value"
                  angleAxisId={0}
                  cornerRadius={7}
                  fill={fill}
                />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center">
                <div className="font-syne text-2xl font-bold leading-none">{score}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5">/ 100</div>
              </div>
            </div>
          </div>

          {/* Distribution badges */}
          <div className="flex flex-wrap gap-1.5 mt-3">
            {Object.entries(current.distribution).map(([key, val]) => {
              const cfg = SENTIMENT_LABELS[key] ?? { label: key, color: "bg-muted text-muted-foreground border-border" };
              return (
                <span
                  key={key}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${cfg.color}`}
                >
                  {cfg.label}
                  <span className="opacity-70">{val.pct}%</span>
                </span>
              );
            })}
          </div>

          {/* Insight */}
          {data?.insight && (
            <p className="mt-3 text-xs text-muted-foreground italic leading-relaxed">
              {data.insight}
            </p>
          )}
        </>
      )}
    </div>
  );
}
