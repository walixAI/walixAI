import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Lock, BarChart2 } from "lucide-react";
import { useTenantProfitability } from "@/lib/queries/profitability";
import { useMonthExpenseBreakdown } from "@/lib/queries/finance";
import { useTenantUsers } from "@/lib/queries/tenantUsers";
import { useAuth } from "@/hooks/useAuth";
import { ListRowsSkeleton } from "@/components/walix/Skeletons";
import { formatMXN0 } from "@/lib/format/currency";
import { cn } from "@/lib/utils";

const LABEL_STYLES = {
  green:   { chip: "bg-success/10 text-success border-success/20",        bar: "bg-success",        text: "text-success" },
  yellow:  { chip: "bg-warning/10 text-warning border-warning/20",        bar: "bg-warning",        text: "text-warning" },
  orange:  { chip: "bg-orange-100 text-orange-600 border-orange-200",     bar: "bg-orange-500",     text: "text-orange-600" },
  red:     { chip: "bg-danger/10  text-danger  border-danger/20",         bar: "bg-danger",         text: "text-danger" },
  unknown: { chip: "bg-muted text-muted-foreground border-border",        bar: "bg-muted-foreground", text: "text-muted-foreground" },
} as const;

const LABEL_TEXT: Record<string, string> = {
  green:   "Rentable",
  yellow:  "Alerta",
  orange:  "En riesgo",
  red:     "Pérdida",
  unknown: "Sin datos",
};

export function ProfitabilityCard() {
  const { user } = useAuth();
  const [breakdownExpanded, setBreakdownExpanded] = useState(false);

  const canSeeTeam =
    user?.role === "owner" ||
    user?.role === "platform_owner" ||
    user?.role === "gerente";

  const profitability = useTenantProfitability();
  const hasFinanceAccess = !profitability.isError;

  const { data: breakdown, isPending: brkPending } = useMonthExpenseBreakdown(
    hasFinanceAccess,
  );
  const { data: users = [] } = useTenantUsers();

  // ── Loading ────────────────────────────────────────────────────────────────
  if (profitability.isPending) {
    return (
      <div className="rounded-xl border border-border bg-card p-5 shadow-card">
        <div className="flex items-center gap-2 mb-3">
          <BarChart2 className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">Rentabilidad</span>
        </div>
        <ListRowsSkeleton rows={3} showAvatar={false} />
      </div>
    );
  }

  // ── Sin acceso (403) ───────────────────────────────────────────────────────
  if (profitability.isError) {
    return (
      <div className="rounded-xl border border-border bg-card p-5 shadow-card flex flex-col items-center justify-center gap-3 text-center min-h-[180px]">
        <div className="rounded-full bg-muted p-3">
          <Lock className="h-5 w-5 text-muted-foreground" />
        </div>
        <div>
          <p className="text-sm font-semibold">Sin acceso a Finanzas</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Pide a tu administrador acceso al módulo de finanzas.
          </p>
        </div>
      </div>
    );
  }

  const data = profitability.data!;
  const styles = LABEL_STYLES[data.label] ?? LABEL_STYLES.unknown;
  const profitPct = data.profitPct != null ? data.profitPct.toFixed(1) : null;

  function resolveUserName(userId: string): string {
    return users.find((u) => u.id === userId)?.name ?? "—";
  }

  return (
    <div className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
      <div className="p-5 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-primary shrink-0" />
            <span className="text-sm font-semibold">Rentabilidad</span>
          </div>
          <span
            className={cn(
              "text-[11px] font-semibold px-2 py-0.5 rounded-full border",
              styles.chip,
            )}
          >
            {LABEL_TEXT[data.label] ?? data.label}
          </span>
        </div>

        {/* Stats principales */}
        <div className="grid grid-cols-3 gap-3">
          <StatBox label="Ingresos" value={formatMXN0(data.revenue)} />
          <StatBox label="Gastos" value={formatMXN0(data.expenses)} />
          <StatBox
            label="Utilidad"
            value={formatMXN0(data.profit)}
            sub={profitPct != null ? `${profitPct}% margen` : undefined}
            className={styles.text}
          />
        </div>

        {/* Link a finanzas */}
        <Link
          to="/finance"
          className="text-xs font-medium text-primary hover:underline"
        >
          Ver gastos →
        </Link>
      </div>

      {/* Desglose colapsable */}
      {hasFinanceAccess && (
        <div className="border-t border-border">
          <button
            onClick={() => setBreakdownExpanded(!breakdownExpanded)}
            className="w-full flex items-center justify-between px-5 py-3 text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors"
          >
            <span>Desglose de gastos</span>
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 transition-transform",
                breakdownExpanded && "rotate-180",
              )}
            />
          </button>

          {breakdownExpanded && (
            <div className="px-5 pb-4 space-y-3">
              {brkPending ? (
                <ListRowsSkeleton rows={2} showAvatar={false} />
              ) : breakdown ? (
                <>
                  {/* Fijo / Variable / Total */}
                  <div className="grid grid-cols-3 gap-2">
                    <MiniStat label="Fijos" value={formatMXN0(breakdown.fijo)} />
                    <MiniStat label="Variables" value={formatMXN0(breakdown.variable)} />
                    <MiniStat label="Total" value={formatMXN0(breakdown.total)} bold />
                  </div>

                  {/* Por vendedor (solo si canSeeTeam) */}
                  {canSeeTeam && breakdown.bySeller.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                        Por responsable
                      </p>
                      {breakdown.bySeller.map(({ userId, amount }) => (
                        <div
                          key={userId}
                          className="flex items-center justify-between gap-2 text-xs"
                        >
                          <span className="text-muted-foreground truncate">
                            {resolveUserName(userId)}
                          </span>
                          <span className="font-medium shrink-0">
                            {formatMXN0(amount)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs text-muted-foreground">Sin gastos confirmados este mes.</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatBox({
  label,
  value,
  sub,
  className,
}: {
  label: string;
  value: string;
  sub?: string;
  className?: string;
}) {
  return (
    <div className="rounded-lg bg-muted/40 px-3 py-2">
      <p className="text-[10px] text-muted-foreground mb-0.5">{label}</p>
      <p className={cn("text-sm font-semibold", className)}>{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

function MiniStat({
  label,
  value,
  bold,
}: {
  label: string;
  value: string;
  bold?: boolean;
}) {
  return (
    <div>
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className={cn("text-xs", bold ? "font-bold" : "font-medium")}>{value}</p>
    </div>
  );
}
