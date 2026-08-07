import { TrendingDown } from "lucide-react";
import { useReportsExtra } from "@/lib/queries/reports";

function fmt(n: number) {
  return n.toLocaleString("es-MX");
}

export function SalesFunnelChart() {
  const { data, isLoading } = useReportsExtra(30);

  const stages = data?.funnel ?? [];
  const maxDeals = stages.length > 0 ? Math.max(...stages.map((s) => s.deals_reached), 1) : 1;

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center gap-2 mb-4">
        <div className="h-8 w-8 grid place-items-center rounded-lg bg-primary/10 text-primary">
          <TrendingDown className="h-4 w-4" />
        </div>
        <h3 className="text-sm font-semibold">Embudo de conversión</h3>
        {data && (
          <span className="ml-auto text-xs text-muted-foreground">Últimos {data.period_days} días</span>
        )}
      </div>

      {isLoading || !data ? (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-10 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : stages.length === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">Sin datos de etapas en este período</p>
      ) : (
        <div className="space-y-2">
          {stages.map((stage) => {
            const widthPct = (stage.deals_reached / maxDeals) * 100;
            return (
              <div key={stage.stage_name}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-medium truncate max-w-[160px]">{stage.stage_name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {stage.conversion_from_prev != null && (
                      <span className="text-muted-foreground">
                        {stage.conversion_from_prev.toFixed(0)}%
                      </span>
                    )}
                    <span className="font-semibold">{fmt(stage.deals_reached)}</span>
                  </div>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
