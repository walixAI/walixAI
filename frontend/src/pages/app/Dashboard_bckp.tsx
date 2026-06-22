import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { StatusBadge } from "@/components/whatsapp/StatusBadge";
import { KpiCardsSkeleton, ListRowsSkeleton } from "@/components/walix/Skeletons";
import {
  Users, CheckCircle2, TrendingUp, AlertCircle,
} from "lucide-react";

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Buenos dias";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const { data: leadsData, isLoading } = useQuery({
    queryKey: ["leads", "dashboard"],
    queryFn: () => api.listLeads({ all: true }),
    refetchInterval: 15_000,
  });

  const leads = leadsData?.items ?? [];

  const total = leads.length;
  const calificados = leads.filter((l) => l.status === "calificado").length;
  const enCalificacion = leads.filter((l) => l.status === "en_calificacion").length;
  const escalados = leads.filter((l) => l.status === "escalado").length;
  const nuevos = leads.filter((l) => l.status === "nuevo").length;

  const kpis = [
    { label: "Total leads", value: String(total), icon: Users, color: "bg-primary/10 text-primary" },
    { label: "Calificados", value: String(calificados), icon: CheckCircle2, color: "bg-success/10 text-success" },
    { label: "En calificacion", value: String(enCalificacion), icon: TrendingUp, color: "bg-warning/10 text-warning" },
    { label: "Escalados", value: String(escalados), icon: AlertCircle, color: "bg-danger/10 text-danger" },
  ];

  const name = (user?.name ?? "ahi").split(" ")[0];
  const today = new Date().toLocaleDateString("es-MX", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  // Recent leads: last 20 by updated_at desc
  const recentLeads = [...leads]
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, 20);

  return (
    <div className="space-y-6 max-w-[1400px]">
      {/* Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">
          {getGreeting()}, {name}
        </h1>
        <p className="text-sm text-muted-foreground capitalize mt-1">{today}</p>
      </div>

      {/* KPI Cards */}
      {isLoading ? (
        <KpiCardsSkeleton count={4} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {kpis.map((k) => {
            const Icon = k.icon;
            return (
              <div
                key={k.label}
                className="rounded-xl border border-border bg-card p-5 shadow-card hover:shadow-card-hover transition-all"
              >
                <div className="flex items-start justify-between">
                  <div className="text-sm font-medium text-muted-foreground">{k.label}</div>
                  <div className={`h-9 w-9 grid place-items-center rounded-lg ${k.color}`}>
                    <Icon className="h-4 w-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <span className="text-2xl font-bold tracking-tight">{k.value}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Recent Leads */}
      <div className="rounded-xl border border-border bg-card shadow-card">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <h3 className="font-semibold">Leads recientes</h3>
            <p className="text-xs text-muted-foreground">Ultimas actualizaciones · {total} total</p>
          </div>
          {nuevos > 0 && (
            <span className="text-xs font-semibold bg-info/10 text-info border border-info/20 rounded-full px-2 py-0.5">
              {nuevos} nuevos
            </span>
          )}
        </div>

        {isLoading ? (
          <ListRowsSkeleton rows={8} />
        ) : recentLeads.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-muted-foreground">
            Sin leads todavia. Conecta tu WhatsApp Business para empezar.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {recentLeads.map((lead) => (
              <button
                key={lead.id}
                onClick={() => navigate(`/whatsapp?leadId=${lead.id}`)}
                className="w-full text-left flex items-center gap-3 px-5 py-3 hover:bg-muted/50 transition-colors"
              >
                {/* Avatar */}
                <div className="h-9 w-9 rounded-full bg-gradient-brand flex items-center justify-center text-primary-foreground text-xs font-semibold shrink-0">
                  {(lead.name ?? lead.wa_phone)
                    .split(" ")
                    .map((s) => s[0])
                    .slice(0, 2)
                    .join("")
                    .toUpperCase()}
                </div>

                <div className="flex-1 min-w-0 text-sm">
                  <div className="flex items-center gap-2">
                    <p className="font-medium truncate flex-1">{lead.name ?? lead.wa_phone}</p>
                    <StatusBadge status={lead.status} />
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground">
                    <span>{lead.wa_phone}</span>
                    {lead.qualification_score != null && (
                      <>
                        <span>·</span>
                        <span>Score: {lead.qualification_score}</span>
                      </>
                    )}
                    {lead.assigned_to && (
                      <>
                        <span>·</span>
                        <span>Asignado</span>
                      </>
                    )}
                  </div>
                </div>

                <div className="text-[11px] text-muted-foreground shrink-0">
                  {new Date(lead.updated_at).toLocaleString("es-MX", {
                    day: "2-digit",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
