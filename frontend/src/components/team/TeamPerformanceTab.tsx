import { useState } from "react";
import { ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useTeamPerformance } from "@/lib/queries/profitability";
import type { TeamPerformanceMember } from "@/lib/queries/profitability";
import { ListRowsSkeleton } from "@/components/walix/Skeletons";
import { cn } from "@/lib/utils";

// ── Formatters ────────────────────────────────────────────────────────────────

function formatMXN(n: number) {
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 0,
  }).format(n);
}

function formatPct(n: number | null) {
  if (n == null) return "—";
  return `${n.toFixed(1)}%`;
}

const MONTHS_ES = [
  "Enero","Febrero","Marzo","Abril","Mayo","Junio",
  "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre",
];

function prevMonth(y: number, m: number): [number, number] {
  return m === 1 ? [y - 1, 12] : [y, m - 1];
}
function nextMonth(y: number, m: number): [number, number] {
  return m === 12 ? [y + 1, 1] : [y, m + 1];
}

// ── Color helpers ─────────────────────────────────────────────────────────────

function runRateColor(pct: number | null): string {
  if (pct == null) return "text-muted-foreground";
  if (pct >= 100) return "text-success font-semibold";
  if (pct >= 80) return "text-warning font-semibold";
  return "text-danger font-semibold";
}

function marginColor(pct: number | null): string {
  if (pct == null) return "text-muted-foreground";
  if (pct >= 20) return "text-success font-semibold";
  if (pct >= 10) return "text-warning font-semibold";
  return "text-danger font-semibold";
}

// ── Avatar ────────────────────────────────────────────────────────────────────

const AVATAR_COLORS = [
  "bg-violet-500", "bg-blue-500", "bg-teal-500",
  "bg-green-500", "bg-amber-500", "bg-rose-500",
];

function MiniAvatar({ name }: { name: string }) {
  const idx = name.charCodeAt(0) % AVATAR_COLORS.length;
  return (
    <div
      className={cn(
        "h-7 w-7 rounded-full flex items-center justify-center text-xs font-semibold text-white shrink-0",
        AVATAR_COLORS[idx],
      )}
    >
      {name.charAt(0).toUpperCase()}
    </div>
  );
}

// ── Summary tile ──────────────────────────────────────────────────────────────

function SummaryTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3 shadow-card">
      <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-xl font-bold tracking-tight">{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

// ── Sort header ───────────────────────────────────────────────────────────────

type SortKey = "wonAmount" | "runRatePct" | "marginPct";

function SortTh({
  label,
  sortKey,
  current,
  dir,
  onSort,
  className,
}: {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  dir: "asc" | "desc";
  onSort: (k: SortKey) => void;
  className?: string;
}) {
  const active = current === sortKey;
  return (
    <th
      className={cn(
        "px-4 py-3 text-left text-xs font-semibold text-muted-foreground cursor-pointer select-none hover:text-foreground transition-colors",
        active && "text-foreground",
        className,
      )}
      onClick={() => onSort(sortKey)}
    >
      <span className="flex items-center gap-1">
        {label}
        <ArrowUpDown className={cn("h-3 w-3", active ? "text-primary" : "text-muted-foreground/50")} />
      </span>
    </th>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function TeamPerformanceTab() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [sortBy, setSortBy] = useState<SortKey>("wonAmount");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const { data = [], isPending } = useTeamPerformance(true, year, month);

  function handlePrev() { const [y, m] = prevMonth(year, month); setYear(y); setMonth(m); }
  function handleNext() { const [y, m] = nextMonth(year, month); setYear(y); setMonth(m); }

  function handleSort(key: SortKey) {
    if (sortBy === key) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setSortBy(key); setSortDir("desc"); }
  }

  const sorted = [...data].sort((a, b) => {
    const va = (a[sortBy] as number | null) ?? (sortDir === "desc" ? -Infinity : Infinity);
    const vb = (b[sortBy] as number | null) ?? (sortDir === "desc" ? -Infinity : Infinity);
    return sortDir === "desc" ? vb - va : va - vb;
  });

  // ── Summary aggregates ────────────────────────────────────────────────────
  const totalGoal = data.reduce((s, m) => s + (m.assignedGoal ?? 0), 0);
  const totalWon = data.reduce((s, m) => s + m.wonAmount, 0);
  const totalRunRate = data.reduce((s, m) => s + m.runRate, 0);
  const marginsWithData = data.filter((m) => m.marginPct != null);
  const avgMargin =
    marginsWithData.length > 0
      ? marginsWithData.reduce((s, m) => s + m.marginPct!, 0) / marginsWithData.length
      : null;

  return (
    <div className="space-y-5">
      {/* Period selector */}
      <div className="flex items-center gap-2">
        <button
          onClick={handlePrev}
          className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-sm font-semibold min-w-[140px] text-center">
          {MONTHS_ES[month - 1]} {year}
        </span>
        <button
          onClick={handleNext}
          className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Summary tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryTile
          label="Meta equipo"
          value={totalGoal > 0 ? formatMXN(totalGoal) : "—"}
          sub={`${data.filter((m) => m.assignedGoal != null).length} con meta`}
        />
        <SummaryTile
          label="Ganado"
          value={formatMXN(totalWon)}
          sub={totalGoal > 0 ? `${((totalWon / totalGoal) * 100).toFixed(0)}% de meta` : undefined}
        />
        <SummaryTile
          label="Run Rate"
          value={formatMXN(totalRunRate)}
          sub="proyección del mes"
        />
        <SummaryTile
          label="Margen prom."
          value={formatPct(avgMargin)}
          sub="utilidad / ingresos"
        />
      </div>

      {/* Ranking table */}
      <div className="rounded-xl border border-border bg-card overflow-x-auto shadow-card">
        {isPending ? (
          <div className="p-5">
            <ListRowsSkeleton rows={5} />
          </div>
        ) : data.length === 0 ? (
          <p className="px-5 py-12 text-center text-sm text-muted-foreground">
            Sin datos de rendimiento para este periodo.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground">
                  Vendedor
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-muted-foreground">
                  Meta
                </th>
                <SortTh
                  label="Ganado"
                  sortKey="wonAmount"
                  current={sortBy}
                  dir={sortDir}
                  onSort={handleSort}
                  className="text-right"
                />
                <SortTh
                  label="Run Rate"
                  sortKey="runRatePct"
                  current={sortBy}
                  dir={sortDir}
                  onSort={handleSort}
                  className="text-right"
                />
                <th className="px-4 py-3 text-right text-xs font-semibold text-muted-foreground hidden lg:table-cell">
                  Gastos
                </th>
                <SortTh
                  label="Margen"
                  sortKey="marginPct"
                  current={sortBy}
                  dir={sortDir}
                  onSort={handleSort}
                  className="text-right hidden lg:table-cell"
                />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sorted.map((member) => (
                <MemberRow key={member.userId} member={member} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function MemberRow({ member }: { member: TeamPerformanceMember }) {
  return (
    <tr className="hover:bg-muted/20 transition-colors">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2.5">
          <MiniAvatar name={member.name} />
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{member.name}</p>
            {member.email && (
              <p className="text-[11px] text-muted-foreground truncate">{member.email}</p>
            )}
          </div>
        </div>
      </td>
      <td className="px-4 py-3 text-right text-sm text-muted-foreground">
        {member.assignedGoal != null ? formatMXN(member.assignedGoal) : "—"}
      </td>
      <td className="px-4 py-3 text-right">
        <span className="text-sm font-medium">{formatMXN(member.wonAmount)}</span>
      </td>
      <td className="px-4 py-3 text-right">
        <span className={cn("text-sm", runRateColor(member.runRatePct))}>
          {formatPct(member.runRatePct)}
        </span>
      </td>
      <td className="px-4 py-3 text-right text-sm text-muted-foreground hidden lg:table-cell">
        {member.expenses > 0 ? formatMXN(member.expenses) : "—"}
      </td>
      <td className="px-4 py-3 text-right hidden lg:table-cell">
        <span className={cn("text-sm", marginColor(member.marginPct))}>
          {formatPct(member.marginPct)}
        </span>
      </td>
    </tr>
  );
}
