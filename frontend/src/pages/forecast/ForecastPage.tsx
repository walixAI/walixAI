import { useQuery } from "@tanstack/react-query";
import { TrendingUp, AlertTriangle, CheckCircle2, Activity } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { KpiCardsSkeleton } from "@/components/walix/Skeletons";
import { LeadScoreBadge } from "@/components/leads/LeadScoreBadge";
import type { ForecastLeadOut } from "@/lib/api";

function LeadRow({ lead }: { lead: ForecastLeadOut }) {
  return (
    <div className="flex items-center gap-3 px-5 py-3">
      <div className="h-8 w-8 rounded-full bg-gradient-brand flex items-center justify-center text-primary-foreground text-[10px] font-semibold shrink-0">
        {(lead.name ?? lead.wa_phone).slice(0, 2).toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{lead.name ?? lead.wa_phone}</p>
        <p className="text-xs text-muted-foreground">{lead.stage_name ?? "—"}</p>
      </div>
      <LeadScoreBadge score={lead.score} />
    </div>
  );
}

export default function ForecastPage() {
  const { user } = useAuthStore();
  const branchId = user?.branch_id ?? undefined;

  const { data, isLoading } = useQuery({
    queryKey: ["forecast", branchId],
    queryFn: () => api.getForecast(branchId),
    refetchInterval: 120_000,
    staleTime: 60_000,
  });

  const pf = data?.pipeline_forecast;
  const total = pf ? pf.high + pf.medium + pf.low : 0;
  const highPct = total > 0 ? Math.round((pf!.high / total) * 100) : 0;

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">Forecast de cierre</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Predicción basada en scores de leads activos
        </p>
      </div>

      {isLoading ? (
        <KpiCardsSkeleton count={4} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            label="Listos para cerrar"
            value={pf?.high ?? 0}
            format="number"
            icon={<CheckCircle2 className="h-4 w-4" />}
          />
          <KpiCard
            label="En proceso"
            value={pf?.medium ?? 0}
            format="number"
            icon={<Activity className="h-4 w-4" />}
          />
          <KpiCard
            label="En riesgo"
            value={pf?.low ?? 0}
            format="number"
            icon={<AlertTriangle className="h-4 w-4" />}
          />
          <KpiCard
            label="Tasa de calidad"
            value={highPct}
            format="percent"
            icon={<TrendingUp className="h-4 w-4" />}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* High probability leads */}
        <div className="rounded-xl border border-border bg-card shadow-card">
          <div className="px-5 py-4 border-b border-border flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-success" />
            <p className="font-semibold text-sm">Listos para cerrar</p>
            <span className="ml-auto text-xs bg-success/10 text-success font-semibold px-2 py-0.5 rounded-full">
              score ≥ 70
            </span>
          </div>
          {isLoading ? (
            <div className="p-5 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />
              ))}
            </div>
          ) : (data?.high_probability_leads ?? []).length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              Sin leads listos para cerrar en este momento
            </div>
          ) : (
            <div className="divide-y divide-border">
              {data!.high_probability_leads.map((lead) => (
                <LeadRow key={lead.lead_id} lead={lead} />
              ))}
            </div>
          )}
        </div>

        {/* At-risk leads */}
        <div className="rounded-xl border border-danger/20 bg-card shadow-card">
          <div className="px-5 py-4 border-b border-danger/20 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-danger" />
            <p className="font-semibold text-sm">Leads en riesgo</p>
            <span className="ml-auto text-xs bg-danger/10 text-danger font-semibold px-2 py-0.5 rounded-full">
              score &lt; 30
            </span>
          </div>
          {isLoading ? (
            <div className="p-5 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />
              ))}
            </div>
          ) : (data?.at_risk_leads ?? []).length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              Sin leads en riesgo — buen trabajo
            </div>
          ) : (
            <div className="divide-y divide-border/50">
              {data!.at_risk_leads.map((lead) => (
                <LeadRow key={lead.lead_id} lead={lead} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
