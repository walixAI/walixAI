import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import { formatMXN } from "@/lib/queries/pipeline";
import { cn } from "@/lib/utils";

interface Props {
  total: number;
  weighted: number;
  closingThisMonth: number;
  closingDeltaPct: number | null;
  activeCount: number;
}

export function ForecastKpis({ total, weighted, closingThisMonth, closingDeltaPct, activeCount }: Props) {
  const trend =
    closingDeltaPct === null ? "flat" : closingDeltaPct > 1 ? "up" : closingDeltaPct < -1 ? "down" : "flat";
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
      <Kpi
        label="Pipeline total"
        value={`${formatMXN(total)} MXN`}
        sub={`${activeCount} oportunidades activas`}
      />
      <Divider />
      <Kpi
        label="Ponderado por probabilidad"
        value={`${formatMXN(weighted)} MXN`}
        sub="Forecast esperado"
        valueClassName="text-primary"
      />
      <Divider />
      <Kpi
        label="Cierre este mes"
        value={`${formatMXN(closingThisMonth)} MXN`}
        sub={
          <span className={cn(
            "inline-flex items-center gap-1",
            trend === "up" && "text-success",
            trend === "down" && "text-danger",
            trend === "flat" && "text-muted-foreground",
          )}>
            <TrendIcon className="h-3 w-3" />
            {closingDeltaPct === null ? "Sin histórico" : `${closingDeltaPct > 0 ? "+" : ""}${closingDeltaPct.toFixed(0)}% vs mes anterior`}
          </span>
        }
        valueClassName="text-success"
      />
    </div>
  );
}

function Kpi({ label, value, sub, valueClassName }: { label: string; value: string; sub: React.ReactNode; valueClassName?: string }) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground font-medium">{label}</span>
      <span className={cn("font-bold text-foreground", valueClassName)}>{value}</span>
      <span className="text-[11px] text-muted-foreground">{sub}</span>
    </div>
  );
}

function Divider() {
  return <span className="hidden sm:block h-9 w-px bg-border" />;
}
