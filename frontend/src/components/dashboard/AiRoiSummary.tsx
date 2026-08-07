import { Link } from "react-router-dom";
import { Sparkles, ArrowRight } from "lucide-react";
import { useRoiSummary } from "@/lib/queries/metrics";

function fmtPct(n: number) {
  return `${n.toFixed(1)}%`;
}

function fmtMXN(n: number | null) {
  if (n == null) return "N/A";
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 0,
  }).format(n);
}

export function AiRoiSummary() {
  const { data, isLoading } = useRoiSummary(30);

  const metrics = data
    ? [
        { label: "Tasa de calificación bot", value: fmtPct(data.bot_qualification_rate) },
        { label: "Tasa de conversión", value: fmtPct(data.conversion_rate) },
        { label: "Horas ahorradas (30 días)", value: `${data.estimated_hours_saved.toFixed(1)} h` },
        { label: "Ingreso estimado", value: fmtMXN(data.estimated_revenue) },
      ]
    : [];

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 grid place-items-center rounded-lg bg-primary/10 text-primary">
            <Sparkles className="h-4 w-4" />
          </div>
          <h3 className="text-sm font-semibold">Impacto del copiloto IA</h3>
        </div>
        <Link
          to="/roi"
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Ver ROI completo <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      {isLoading || !data ? (
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {metrics.map((m) => (
            <div key={m.label} className="rounded-lg border border-border px-3 py-2.5">
              <p className="text-xs text-muted-foreground truncate">{m.label}</p>
              <p className="mt-1 text-lg font-bold tracking-tight">{m.value}</p>
            </div>
          ))}
        </div>
      )}

      {data && (
        <p className="mt-3 text-xs text-muted-foreground text-right">{data.period_label}</p>
      )}
    </div>
  );
}
