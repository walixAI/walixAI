import { cn } from "@/lib/utils";
import type { OppForecastRead } from "@/lib/api";

function formatMXN(n: string | number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const val = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(val)) return "—";
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function TrendArrow({ trend }: { trend: "up" | "down" | "flat" }) {
  if (trend === "up")
    return <span className="text-success font-semibold text-sm">▲</span>;
  if (trend === "down")
    return <span className="text-danger font-semibold text-sm">▼</span>;
  return <span className="text-muted-foreground font-semibold text-sm">=</span>;
}

interface KpiProps {
  label: string;
  value: string;
  sub?: React.ReactNode;
  className?: string;
}

function Kpi({ label, value, sub, className }: KpiProps) {
  return (
    <div className={cn("flex flex-col gap-0.5 px-6 py-3", className)}>
      <p className="text-[11px] text-muted-foreground uppercase tracking-wide font-medium">
        {label}
      </p>
      <p className="text-lg font-bold tabular-nums">{value}</p>
      {sub && <div className="text-[11px] text-muted-foreground flex items-center gap-1">{sub}</div>}
    </div>
  );
}

export function ForecastBar({ forecast }: { forecast: OppForecastRead | null }) {
  if (!forecast) {
    return (
      <div className="rounded-xl border border-border bg-card/80 flex animate-pulse h-[64px]" />
    );
  }

  const wonTotal = (forecast.stages ?? [])
    .filter((s) =>
      s.stage_name.toLowerCase().includes("ganad") ||
      s.stage_name.toLowerCase().includes("cerrad") ||
      s.stage_name.toLowerCase().includes("won")
    )
    .reduce((acc, s) => acc + parseFloat(s.total_amount || "0"), 0);

  return (
    <div className="rounded-xl border border-border bg-card/80 flex divide-x divide-border overflow-hidden">
      <Kpi
        label="Pipeline Total"
        value={formatMXN(forecast.pipeline_total)}
        sub={
          <>
            <TrendArrow trend={forecast.trend} />
            <span>vs mes anterior</span>
          </>
        }
      />
      <Kpi
        label="Ponderado"
        value={formatMXN(forecast.weighted_total)}
        sub={
          <>
            <span className="text-muted-foreground">
              {forecast.active_count} oportunidades activas
            </span>
          </>
        }
      />
      <Kpi
        label="Ganado este mes"
        value={wonTotal > 0 ? formatMXN(String(wonTotal)) : "—"}
        sub={
          wonTotal > 0 ? (
            <span className="text-success font-medium">✓ Cerrado</span>
          ) : (
            <span className="text-muted-foreground">Sin cierres aún</span>
          )
        }
      />
    </div>
  );
}
