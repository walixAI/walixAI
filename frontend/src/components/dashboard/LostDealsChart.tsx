import { XCircle } from "lucide-react";
import { useReportsExtra } from "@/lib/queries/reports";

function fmtMXN(n: number) {
  return n.toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
}

export function LostDealsChart() {
  const { data, isLoading } = useReportsExtra(30);

  const reasons = data?.lost_reasons ?? [];
  const maxCount = reasons.length > 0 ? Math.max(...reasons.map((r) => r.count), 1) : 1;

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center gap-2 mb-4">
        <div className="h-8 w-8 grid place-items-center rounded-lg bg-danger/10 text-danger">
          <XCircle className="h-4 w-4" />
        </div>
        <h3 className="text-sm font-semibold">Razones de pérdida</h3>
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
      ) : reasons.length === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">Sin deals perdidos en este período</p>
      ) : (
        <div className="space-y-3">
          {reasons.map((r) => {
            const widthPct = (r.count / maxCount) * 100;
            return (
              <div key={r.reason}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-medium truncate max-w-[160px]">{r.reason}</span>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-muted-foreground">{r.count} deals</span>
                    {r.lost_amount > 0 && (
                      <span className="font-semibold text-danger">{fmtMXN(r.lost_amount)}</span>
                    )}
                  </div>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-danger/60 transition-all"
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
