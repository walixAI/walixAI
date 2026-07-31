import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Target, TrendingUp } from "lucide-react";
import { useTenantRunRate } from "@/lib/queries/profitability";
import { useRunRateBySeller } from "@/lib/queries/profitability";
import { useAuth } from "@/hooks/useAuth";
import { ListRowsSkeleton } from "@/components/walix/Skeletons";
import { cn } from "@/lib/utils";

function formatMXN(n: number) {
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 0,
  }).format(n);
}

const STATUS_STYLES = {
  green:  { chip: "bg-success/10 text-success border-success/20",   bar: "bg-success" },
  yellow: { chip: "bg-warning/10 text-warning border-warning/20",   bar: "bg-warning" },
  red:    { chip: "bg-danger/10  text-danger  border-danger/20",    bar: "bg-danger"  },
} as const;

interface Props {
  compact?: boolean;
  showSellers?: boolean;
}

export function RunRateCard({ compact = false, showSellers = false }: Props) {
  const { user } = useAuth();
  const [sellersExpanded, setSellersExpanded] = useState(false);

  // Solo owner/platform_owner pueden ver datos individuales de otros
  const canSeeOwnerData =
    user?.role === "owner" || user?.role === "platform_owner";

  const { data, isPending } = useTenantRunRate();
  const { data: sellers = [] } = useRunRateBySeller(
    showSellers && canSeeOwnerData,
  );

  if (isPending) {
    return (
      <div className="rounded-xl border border-border bg-card p-5 shadow-card">
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">Run Rate</span>
        </div>
        <ListRowsSkeleton rows={3} showAvatar={false} />
      </div>
    );
  }

  if (!data) return null;

  const styles = STATUS_STYLES[data.status] ?? STATUS_STYLES.red;
  const pct = Math.min(100, Math.max(0, data.pctOfGoal ?? 0));
  const hasGoal = data.goalAmount != null;
  const recommendations = compact
    ? data.recommendations.slice(0, 3)
    : data.recommendations;

  return (
    <div className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
      <div className="p-5 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary shrink-0" />
            <span className="text-sm font-semibold">Run Rate</span>
          </div>
          <span
            className={cn(
              "text-[11px] font-semibold px-2 py-0.5 rounded-full border",
              styles.chip,
            )}
          >
            {data.status === "green"
              ? "En meta"
              : data.status === "yellow"
                ? "En riesgo"
                : "Por debajo"}
          </span>
        </div>

        {/* Valor grande */}
        <div>
          <p className="text-[11px] text-muted-foreground mb-0.5">Proyección del mes</p>
          <p className="text-2xl font-bold tracking-tight">{formatMXN(data.runRate)}</p>
        </div>

        {/* Barra de progreso */}
        {hasGoal && (
          <div className="space-y-1">
            <div className="flex justify-between text-[11px] text-muted-foreground">
              <span>{pct.toFixed(0)}% de la meta</span>
              <span>{formatMXN(data.goalAmount!)}</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={cn("h-full rounded-full transition-all", styles.bar)}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}

        {/* Estado vacío — sin meta */}
        {!hasGoal && (
          <div className="rounded-lg border border-dashed border-border p-3 text-center space-y-1">
            <Target className="h-5 w-5 text-muted-foreground mx-auto" />
            <p className="text-xs text-muted-foreground">Sin meta mensual definida</p>
            <Link
              to="/settings?tab=metas"
              className="text-xs font-medium text-primary hover:underline"
            >
              Ir a Metas →
            </Link>
          </div>
        )}

        {/* Stats grid */}
        <div className={cn("grid gap-3", compact ? "grid-cols-3" : "grid-cols-4")}>
          <Stat label="Vendido" value={formatMXN(data.wonRevenue)} />
          <Stat label="Meta" value={hasGoal ? formatMXN(data.goalAmount!) : "—"} />
          <Stat label="Esperado hoy" value={formatMXN(data.expectedToday)} />
          {!compact && (
            <Stat
              label="Gap"
              value={formatMXN(Math.abs(data.gap))}
              sub={data.gap >= 0 ? "a favor" : "por cubrir"}
              danger={data.gap < 0}
            />
          )}
        </div>

        {/* Recomendaciones */}
        {recommendations.length > 0 && (
          <ul className="space-y-1">
            {recommendations.map((rec, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                <span className="shrink-0 mt-0.5 text-primary">•</span>
                {rec}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Detalle por vendedor */}
      {showSellers && canSeeOwnerData && sellers.length > 0 && (
        <div className="border-t border-border">
          <button
            onClick={() => setSellersExpanded(!sellersExpanded)}
            className="w-full flex items-center justify-between px-5 py-3 text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors"
          >
            <span>Detalle por vendedor ({sellers.length})</span>
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform",
                sellersExpanded && "rotate-180",
              )}
            />
          </button>
          {sellersExpanded && (
            <div className="divide-y divide-border">
              {sellers.map((s) => {
                const spct = Math.min(100, Math.max(0, s.pctOfGoal ?? 0));
                return (
                  <div key={s.userId} className="px-5 py-2.5 space-y-1">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-medium truncate">{s.name}</span>
                      <span className="shrink-0 text-muted-foreground">
                        {formatMXN(s.wonRevenue)}
                      </span>
                    </div>
                    {s.userGoal != null && (
                      <div className="space-y-0.5">
                        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                          <div
                            className="h-full rounded-full bg-primary/60"
                            style={{ width: `${spct}%` }}
                          />
                        </div>
                        <p className="text-[10px] text-muted-foreground">
                          {spct.toFixed(0)}% de {formatMXN(s.userGoal)}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  danger,
}: {
  label: string;
  value: string;
  sub?: string;
  danger?: boolean;
}) {
  return (
    <div className="rounded-lg bg-muted/40 px-3 py-2">
      <p className="text-[10px] text-muted-foreground mb-0.5">{label}</p>
      <p className={cn("text-sm font-semibold", danger && "text-danger")}>{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
    </div>
  );
}
