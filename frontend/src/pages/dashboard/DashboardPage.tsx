import { useQuery } from "@tanstack/react-query";
import {
  Users, TrendingUp, MessageSquare, Zap,
  CheckCircle2, AlertTriangle, Activity, Cpu,
  Wifi, WifiOff, DollarSign, BarChart3,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  DashboardAsesor, DashboardGerente, DashboardOwner, DashboardIT,
} from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { SentimentWidget } from "@/components/dashboard/SentimentWidget";
import { MetricsTrendChart } from "@/components/dashboard/MetricsTrendChart";
import { KpiCardsSkeleton } from "@/components/walix/Skeletons";

// ── Shared helpers ────────────────────────────────────────────────────────────

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Buenos días";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

function isToday(iso: string): boolean {
  return new Date(iso).toDateString() === new Date().toDateString();
}

const AGENT_TYPE_LABELS: Record<string, string> = {
  follow_up: "Seguimiento",
  pipeline:  "Pipeline",
  closing:   "Cierre",
  config:    "Configuración",
};

// ── Asesor view ───────────────────────────────────────────────────────────────

function AsesorView({ data }: { data: DashboardAsesor }) {
  const activeCount    = data.my_leads.length;
  const atRiskCount    = data.my_leads.filter((l) => l.current_score !== null && l.current_score < 30).length;
  const todayActivity  = data.recent_activity.filter((a) => isToday(a.created_at)).length;
  const suggestCount   = data.pending_suggestions.length;

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Leads activos" value={activeCount} format="number" icon={<Users className="h-4 w-4" />} />
        <KpiCard label="En riesgo" value={atRiskCount} format="number" icon={<AlertTriangle className="h-4 w-4" />} />
        <KpiCard label="Actividades hoy" value={todayActivity} format="number" icon={<Activity className="h-4 w-4" />} />
        <KpiCard label="Sugerencias IA" value={suggestCount} format="number" icon={<Zap className="h-4 w-4" />} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* My leads list */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-card shadow-card">
          <div className="px-5 py-4 border-b border-border">
            <p className="font-semibold text-sm">Mis leads</p>
            <p className="text-xs text-muted-foreground">{activeCount} activos asignados a ti</p>
          </div>
          {data.my_leads.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-muted-foreground">
              Sin leads asignados en este momento
            </div>
          ) : (
            <div className="divide-y divide-border">
              {data.my_leads.map((lead) => (
                <div key={lead.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="h-8 w-8 rounded-full bg-gradient-brand flex items-center justify-center text-primary-foreground text-[10px] font-semibold shrink-0">
                    {(lead.name ?? lead.wa_phone).slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{lead.name ?? lead.wa_phone}</p>
                    <p className="text-xs text-muted-foreground">{lead.stage_name ?? lead.status}</p>
                  </div>
                  {lead.current_score !== null && (
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                      lead.current_score >= 70
                        ? "bg-success/10 text-success"
                        : lead.current_score >= 30
                        ? "bg-warning/10 text-warning"
                        : "bg-danger/10 text-danger"
                    }`}>
                      {lead.current_score}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Suggestions + mini pipeline */}
        <div className="space-y-4">
          {/* Pending suggestions */}
          <div className="rounded-xl border border-border bg-card shadow-card p-5">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">Sugerencias IA</p>
            {data.pending_suggestions.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sin sugerencias pendientes</p>
            ) : (
              <div className="space-y-3">
                {data.pending_suggestions.map((s) => (
                  <div key={s.id} className="text-sm">
                    <span className="inline-block text-[10px] font-semibold uppercase tracking-wide bg-primary/10 text-primary rounded px-1.5 py-0.5 mb-1">
                      {AGENT_TYPE_LABELS[s.agent_type] ?? s.agent_type}
                    </span>
                    <p className="text-xs text-foreground/80 leading-relaxed">{s.suggestion_text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Mini pipeline */}
          <div className="rounded-xl border border-border bg-card shadow-card p-5">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">Mi pipeline</p>
            {data.mini_pipeline.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sin etapas configuradas</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {data.mini_pipeline.map((stage, i) => (
                  <span
                    key={stage.stage_id ?? i}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-secondary text-secondary-foreground border border-border"
                  >
                    <span>{stage.stage_name ?? "Sin etapa"}</span>
                    <span className="font-bold text-foreground">{stage.count}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Gerente view ──────────────────────────────────────────────────────────────

function GerenteView({ data, branchId }: { data: DashboardGerente; branchId: string | null }) {
  const totalWon      = data.team_performance.reduce((s, a) => s + a.leads_won, 0);
  const avgConversion = data.team_performance.length
    ? data.team_performance.reduce((s, a) => s + a.conversion_rate, 0) / data.team_performance.length
    : 0;
  const sentimentScore = data.sentiment_summary.overall_score != null
    ? Math.round(data.sentiment_summary.overall_score * 100)
    : null;

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Total en pipeline"   value={data.pipeline.total_active} format="number"  icon={<TrendingUp className="h-4 w-4" />} />
        <KpiCard label="Cierres del equipo"  value={totalWon}                   format="number"  icon={<CheckCircle2 className="h-4 w-4" />} />
        <KpiCard label="Tasa de conversión"  value={avgConversion}              format="percent" icon={<BarChart3 className="h-4 w-4" />} />
        <KpiCard label="Sentimiento"         value={sentimentScore ?? 0}        format="number"  icon={<MessageSquare className="h-4 w-4" />} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Team performance table */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-card shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <p className="font-semibold text-sm">Rendimiento del equipo</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Asesor</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Asignados</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Cierres</th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Conversión</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.team_performance.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-5 py-8 text-center text-muted-foreground">
                      Sin asesores activos en esta sucursal
                    </td>
                  </tr>
                ) : (
                  data.team_performance.map((a) => (
                    <tr key={a.asesor_id} className="hover:bg-muted/30 transition-colors">
                      <td className="px-5 py-3 font-medium">{a.name}</td>
                      <td className="px-4 py-3 text-right text-muted-foreground">{a.leads_assigned}</td>
                      <td className="px-4 py-3 text-right text-muted-foreground">{a.leads_won}</td>
                      <td className="px-5 py-3 text-right">
                        <span className={`font-semibold ${a.conversion_rate >= 20 ? "text-success" : a.conversion_rate >= 10 ? "text-warning" : "text-muted-foreground"}`}>
                          {a.conversion_rate.toFixed(1)}%
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Sentiment widget */}
        <SentimentWidget branchId={branchId} />
      </div>

      {/* At-risk leads */}
      {data.at_risk_leads.length > 0 && (
        <div className="rounded-xl border border-danger/20 bg-danger/5 shadow-card">
          <div className="px-5 py-4 border-b border-danger/20 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-danger" />
            <p className="font-semibold text-sm text-danger">Leads en riesgo</p>
            <span className="ml-auto text-xs text-danger/70">score &lt; 30</span>
          </div>
          <div className="divide-y divide-danger/10">
            {data.at_risk_leads.map((lead) => (
              <div key={lead.lead_id} className="flex items-center gap-3 px-5 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{lead.name ?? lead.lead_id.slice(0, 8)}</p>
                  <p className="text-xs text-muted-foreground">{lead.stage_name ?? "—"}</p>
                </div>
                <span className="text-xs font-bold text-danger bg-danger/10 px-2 py-0.5 rounded-full">
                  {lead.score}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Owner view ────────────────────────────────────────────────────────────────

function OwnerView({ data }: { data: DashboardOwner }) {
  const totalActive = data.branches.reduce((s, b) => s + b.leads_active, 0);
  const { this_month, last_month } = data.conversion_comparison;
  const conversionDelta = last_month.rate > 0
    ? ((this_month.rate - last_month.rate) / last_month.rate) * 100
    : null;
  const closingsDelta = last_month.won > 0
    ? ((this_month.won - last_month.won) / last_month.won) * 100
    : null;
  const firstBranchId = data.branches[0]?.branch_id ?? null;

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Leads activos"      value={totalActive}        format="number"   icon={<Users className="h-4 w-4" />} />
        <KpiCard label="MRR estimado"       value={data.mrr_estimate}  format="currency" icon={<DollarSign className="h-4 w-4" />} />
        <KpiCard label="Conversión global"  value={this_month.rate}    format="percent"  delta_pct={conversionDelta} icon={<TrendingUp className="h-4 w-4" />} />
        <KpiCard label="Cierres este mes"   value={this_month.won}     format="number"   delta_pct={closingsDelta} icon={<CheckCircle2 className="h-4 w-4" />} />
      </div>

      {/* Branches table */}
      <div className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border">
          <p className="font-semibold text-sm">Comparativa de sucursales</p>
          <p className="text-xs text-muted-foreground mt-0.5">Mes actual · {data.branches.length} sucursales activas</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Sucursal</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Activos</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Creados</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Cerrados</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Conversión</th>
                <th className="text-right px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Sentimiento</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.branches.map((branch) => (
                <tr key={branch.branch_id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-5 py-3 font-medium">{branch.branch_name}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground">{branch.leads_active}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground">{branch.leads_created_month}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground">{branch.leads_won_month}</td>
                  <td className="px-4 py-3 text-right">
                    <span className={`font-semibold ${branch.conversion_rate >= 20 ? "text-success" : branch.conversion_rate >= 10 ? "text-warning" : "text-muted-foreground"}`}>
                      {branch.conversion_rate.toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-5 py-3 text-right">
                    {branch.sentiment_score != null ? (
                      <span className={`text-xs font-semibold ${
                        branch.sentiment_score >= 0.7 ? "text-success" : branch.sentiment_score >= 0.5 ? "text-warning" : "text-danger"
                      }`}>
                        {Math.round(branch.sentiment_score * 100)}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Trend chart */}
      <MetricsTrendChart branchId={firstBranchId} />

      {/* Cross-branch suggestions */}
      {data.cross_branch_suggestions.length > 0 && (
        <div className="rounded-xl border border-border bg-card shadow-card p-5">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">Sugerencias de agentes IA</p>
          <div className="space-y-3">
            {data.cross_branch_suggestions.map((s) => (
              <div key={s.id} className="flex gap-3 text-sm">
                <span className="inline-block shrink-0 text-[10px] font-semibold uppercase tracking-wide bg-primary/10 text-primary rounded px-1.5 py-0.5 self-start mt-0.5">
                  {AGENT_TYPE_LABELS[s.agent_type] ?? s.agent_type}
                </span>
                <p className="text-foreground/80 leading-relaxed">{s.suggestion_text}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── IT view ───────────────────────────────────────────────────────────────────

function ITView({ data }: { data: DashboardIT }) {
  const { integrations } = data;

  return (
    <div className="space-y-6">
      {/* Integration status cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-success/25 bg-success/5 p-5 shadow-card">
          <div className="flex items-center gap-2 mb-3">
            <Wifi className="h-4 w-4 text-success" />
            <p className="text-xs font-medium text-success uppercase tracking-wide">WhatsApp activo</p>
          </div>
          <div className="font-syne text-[2rem] font-bold text-success leading-none">
            {integrations.branches_with_wa}
          </div>
          <p className="text-xs text-muted-foreground mt-1">sucursales conectadas</p>
        </div>

        <div className={`rounded-xl p-5 shadow-card ${integrations.branches_without_wa > 0 ? "border border-danger/25 bg-danger/5" : "border border-border bg-card"}`}>
          <div className="flex items-center gap-2 mb-3">
            <WifiOff className={`h-4 w-4 ${integrations.branches_without_wa > 0 ? "text-danger" : "text-muted-foreground"}`} />
            <p className={`text-xs font-medium uppercase tracking-wide ${integrations.branches_without_wa > 0 ? "text-danger" : "text-muted-foreground"}`}>Sin WhatsApp</p>
          </div>
          <div className={`font-syne text-[2rem] font-bold leading-none ${integrations.branches_without_wa > 0 ? "text-danger" : "text-foreground"}`}>
            {integrations.branches_without_wa}
          </div>
          <p className="text-xs text-muted-foreground mt-1">sucursales sin credenciales</p>
        </div>

        <KpiCard label="Tokens usados (mes)" value={data.ai_token_usage_month} format="number" icon={<Cpu className="h-4 w-4" />} />
        <KpiCard label="Comandos AI (24 h)"  value={data.ai_command_logs_24h}  format="number" icon={<Activity className="h-4 w-4" />} />
      </div>

      {/* Stats row */}
      {data.webhook_errors_24h > 0 && (
        <div className="rounded-xl border border-warning/25 bg-warning/5 p-4 flex items-center gap-3">
          <AlertTriangle className="h-4 w-4 text-warning shrink-0" />
          <p className="text-sm text-warning font-medium">
            {data.webhook_errors_24h} errores de webhook en las últimas 24 h
          </p>
        </div>
      )}

      {/* Config alerts */}
      {data.config_alerts.length > 0 && (
        <div className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-warning" />
            <p className="font-semibold text-sm">Alertas de configuración</p>
            <span className="ml-auto text-xs bg-warning/10 text-warning font-semibold px-2 py-0.5 rounded-full">
              {data.config_alerts.length}
            </span>
          </div>
          <div className="divide-y divide-border">
            {data.config_alerts.map((alert) => (
              <div key={alert.branch_id} className="flex items-center gap-3 px-5 py-3">
                <WifiOff className="h-4 w-4 text-danger shrink-0" />
                <div>
                  <p className="text-sm font-medium">{alert.branch_name}</p>
                  <p className="text-xs text-muted-foreground">Credenciales de WhatsApp Business no configuradas</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.config_alerts.length === 0 && (
        <div className="rounded-xl border border-success/20 bg-success/5 p-5 flex items-center gap-3">
          <CheckCircle2 className="h-5 w-5 text-success" />
          <div>
            <p className="text-sm font-semibold text-success">Todas las integraciones activas</p>
            <p className="text-xs text-muted-foreground">{integrations.total_branches} sucursales configuradas correctamente</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { user } = useAuthStore();
  const role = user?.role ?? "asesor";
  const name = (user?.name ?? "").split(" ")[0];

  const today = new Date().toLocaleDateString("es-MX", {
    weekday: "long", day: "numeric", month: "long",
  });

  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.getDashboard(),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  return (
    <div className="space-y-6 max-w-[1400px]">
      {/* Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">
          {getGreeting()}, {name}
        </h1>
        <p className="text-sm text-muted-foreground capitalize mt-1">{today}</p>
      </div>

      {isLoading && <KpiCardsSkeleton count={4} />}

      {!isLoading && data && (
        <>
          {(data.role === "asesor") && (
            <AsesorView data={data} />
          )}
          {data.role === "gerente" && (
            <GerenteView data={data} branchId={user?.branch_id ?? null} />
          )}
          {data.role === "owner" && (
            <OwnerView data={data} />
          )}
          {data.role === "it" && (
            <ITView data={data} />
          )}
        </>
      )}
    </div>
  );
}
