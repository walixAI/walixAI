import { Link } from "react-router-dom";
import { Users, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTeamPerformance } from "@/lib/queries/profitability";

const LABEL_COLOR: Record<string, string> = {
  green:   "bg-success/15 text-success",
  yellow:  "bg-warning/15 text-warning",
  orange:  "bg-orange-500/15 text-orange-500",
  red:     "bg-danger/15 text-danger",
  unknown: "bg-muted text-muted-foreground",
};

const LABEL_TEXT: Record<string, string> = {
  green:   "En meta",
  yellow:  "Cerca",
  orange:  "En riesgo",
  red:     "Bajo",
  unknown: "—",
};

function fmt(n: number | null) {
  if (n == null) return "—";
  return `${n.toFixed(0)}%`;
}

export function TeamPerformanceSummary() {
  const { data, isLoading } = useTeamPerformance();

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 grid place-items-center rounded-lg bg-primary/10 text-primary">
            <Users className="h-4 w-4" />
          </div>
          <h3 className="text-sm font-semibold">Rendimiento del equipo</h3>
        </div>
        <Link
          to="/settings/team?tab=performance"
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Ver equipo completo <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      {isLoading || !data ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : data.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4 text-center">Sin datos de equipo este período</p>
      ) : (
        <div className="space-y-2">
          {data.slice(0, 3).map((member) => (
            <div
              key={member.userId}
              className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{member.name}</p>
                <p className="text-xs text-muted-foreground">
                  Run rate: {fmt(member.runRatePct)} &middot; Margen: {fmt(member.marginPct)}
                </p>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2 py-0.5 text-xs font-medium",
                  LABEL_COLOR[member.label] ?? LABEL_COLOR.unknown,
                )}
              >
                {LABEL_TEXT[member.label] ?? "—"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
