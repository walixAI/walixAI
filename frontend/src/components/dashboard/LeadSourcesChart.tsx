import { Layers } from "lucide-react";
import { useReportsExtra } from "@/lib/queries/reports";

function fmtMXN(n: number) {
  return n.toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
}

export function LeadSourcesChart() {
  const { data, isLoading } = useReportsExtra(30);

  const sources = data?.lead_sources ?? [];
  const maxCount = sources.length > 0 ? Math.max(...sources.map((s) => s.count), 1) : 1;

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center gap-2 mb-4">
        <div className="h-8 w-8 grid place-items-center rounded-lg bg-primary/10 text-primary">
          <Layers className="h-4 w-4" />
        </div>
        <h3 className="text-sm font-semibold">Fuentes de leads</h3>
        {data && (
          <span className="ml-auto text-xs text-muted-foreground">Últimos {data.period_days} días</span>
        )}
      </div>

      {isLoading || !data ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-10 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : sources.length === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">Sin datos de fuentes en este período</p>
      ) : (
        <div className="space-y-3">
          {sources.map((src) => {
            const widthPct = (src.count / maxCount) * 100;
            return (
              <div key={src.source}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-medium truncate max-w-[160px]">{src.source}</span>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-muted-foreground">{src.count} deals</span>
                    {src.revenue > 0 && (
                      <span className="font-semibold text-success">{fmtMXN(src.revenue)}</span>
                    )}
                  </div>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary/70 transition-all"
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
