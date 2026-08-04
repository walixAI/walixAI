import { Wallet, Target, MessageSquare, TrendingUp, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { useDashboardKpis } from "@/lib/queries/dashboard";
import { KpiCardsSkeleton } from "@/components/walix/Skeletons";
import { cn } from "@/lib/utils";

function formatMXN(n: number) {
  return new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 }).format(n);
}

export function KpiCardsRow() {
  const { data: kpis, isLoading: kpisLoading } = useDashboardKpis();

  const kpiData = [
    { label: "Valor del Pipeline", value: kpis ? formatMXN(kpis.pipelineValue) : "—", suffix: "MXN", delta: `+${kpis?.pipelineDeltaPct ?? 0}%`, trend: "up" as const, hint: "vs ayer", icon: Wallet },
    { label: "Oportunidades Activas", value: String(kpis?.activeDeals ?? 0), suffix: "abiertas", delta: String(kpis?.staleDeals ?? 0), trend: "down" as const, hint: "sin actividad", icon: Target },
    { label: "Mensajes WhatsApp", value: String(kpis?.messagesToday ?? 0), suffix: "hoy", delta: String(kpis?.messagesUnanswered ?? 0), trend: "down" as const, hint: "sin respuesta", icon: MessageSquare },
    { label: "Tasa de Cierre", value: `${kpis?.closeRate ?? 0}%`, suffix: "", delta: `+${kpis?.closeRateDelta ?? 0}pts`, trend: "up" as const, hint: "este mes", icon: TrendingUp },
  ];

  if (kpisLoading && !kpis) return <KpiCardsSkeleton />;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {kpiData.map((k) => {
        const Icon = k.icon;
        const TrendIcon = k.trend === "up" ? ArrowUpRight : ArrowDownRight;
        return (
          <div
            key={k.label}
            className="rounded-xl border border-border bg-card p-5 shadow-card hover:shadow-card-hover transition-all"
          >
            <div className="flex items-start justify-between">
              <div className="text-sm font-medium text-muted-foreground">{k.label}</div>
              <div className="h-9 w-9 grid place-items-center rounded-lg bg-primary/10 text-primary">
                <Icon className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-1.5">
              <span className="text-2xl font-bold tracking-tight">{k.value}</span>
              {k.suffix && <span className="text-xs text-muted-foreground">{k.suffix}</span>}
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 text-xs">
              <span className={cn(
                "inline-flex items-center gap-0.5 font-semibold",
                k.trend === "up" ? "text-success" : "text-danger"
              )}>
                <TrendIcon className="h-3 w-3" />
                {k.delta}
              </span>
              <span className="text-muted-foreground">{k.hint}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
