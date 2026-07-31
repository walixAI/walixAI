import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  useDashboardKpis, useRecentActivity,
  usePipelineByStage, useDealsClosedTimeline,
} from "@/lib/queries/dashboard";
import { relativeTime } from "@/lib/format/relativeTime";
import {
  Wallet, Target, MessageSquare, TrendingUp, ArrowUpRight, ArrowDownRight,
  Sparkles, AlertTriangle, X, Clock,
  MoveRight, FileText, StickyNote, CheckCircle2,
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  AreaChart, Area, Cell,
} from "recharts";
import { cn } from "@/lib/utils";
import { KpiCardsSkeleton, ListRowsSkeleton } from "@/components/walix/Skeletons";

// ── FASE 2 (IA) — reintroducir cuando portemos esas piezas ──────────────────
// import { useCopilot } from "@/store/copilot";
// import { DashboardAiSection } from "@/components/walix/DashboardAiSection";
// import { MorningBriefing } from "@/components/walix/MorningBriefing";
import { ProactiveBriefing } from "@/components/walix/ProactiveBriefing";
import { TaskCards } from "@/components/dashboard/TaskCards";
import { AIPatternsCard } from "@/components/walix/AIPatternsCard";
import { RunRateCard } from "@/components/walix/RunRateCard";
import { ProfitabilityCard } from "@/components/walix/ProfitabilityCard";

const activityIcon: Record<string, { icon: typeof MoveRight; color: string }> = {
  deal: { icon: MoveRight, color: "text-primary bg-primary/10" },
  wa_sent: { icon: FileText, color: "text-accent bg-accent/10" },
  wa_received: { icon: FileText, color: "text-success bg-success/10" },
  note: { icon: StickyNote, color: "text-warning bg-warning/10" },
  task: { icon: CheckCircle2, color: "text-success bg-success/10" },
};

function formatMXN(n: number) {
  return new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 }).format(n);
}

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Buenos días";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

const stageColors = [
  "hsl(239 84% 85%)",
  "hsl(239 84% 75%)",
  "hsl(239 84% 65%)",
  "hsl(239 84% 55%)",
  "hsl(239 84% 45%)",
  "hsl(239 84% 35%)",
];

export default function Dashboard() {
  const { user } = useAuth();
  const canSeeTeam =
    user?.role === "owner" ||
    user?.role === "platform_owner" ||
    user?.role === "gerente";
  const [showAlert, setShowAlert] = useState(true);

  const { data: kpis, isLoading: kpisLoading } = useDashboardKpis();
  const { data: activity = [], isLoading: activityLoading } = useRecentActivity(10);
  const { data: pipelineByStage = [] } = usePipelineByStage();
  const { data: dealsTimeline = [] } = useDealsClosedTimeline(30);

  const atRiskDealsCount = kpis?.staleDeals ?? 0;
  const kpiData = [
    { label: "Valor del Pipeline", value: kpis ? formatMXN(kpis.pipelineValue) : "—", suffix: "MXN", delta: `+${kpis?.pipelineDeltaPct ?? 0}%`, trend: "up" as const, hint: "vs ayer", icon: Wallet },
    { label: "Oportunidades Activas", value: String(kpis?.activeDeals ?? 0), suffix: "abiertas", delta: String(kpis?.staleDeals ?? 0), trend: "down" as const, hint: "sin actividad", icon: Target },
    { label: "Mensajes WhatsApp", value: String(kpis?.messagesToday ?? 0), suffix: "hoy", delta: String(kpis?.messagesUnanswered ?? 0), trend: "down" as const, hint: "sin respuesta", icon: MessageSquare },
    { label: "Tasa de Cierre", value: `${kpis?.closeRate ?? 0}%`, suffix: "", delta: `+${kpis?.closeRateDelta ?? 0}pts`, trend: "up" as const, hint: "este mes", icon: TrendingUp },
  ];

  // Nombre del usuario desde authStore (sustituye la query a `profiles` de Supabase).
  // Ajusta los campos a la forma real de tu objeto user si difiere.
  const displayName =
    (user as any)?.full_name ??
    (user as any)?.name ??
    user?.email?.split("@")[0] ??
    "ahí";
  const name = displayName.split(" ")[0];
  const today = new Date().toLocaleDateString("es-MX", {
    weekday: "long", day: "numeric", month: "long",
  });

  return (
    <div className="space-y-6 max-w-[1400px]">
      {/* FASE 2: <MorningBriefing /> */}

      {/* Risk alert */}
      {showAlert && atRiskDealsCount > 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm">
          <AlertTriangle className="h-5 w-5 text-warning shrink-0" />
          <div className="flex-1 text-foreground">
            <strong>{atRiskDealsCount} oportunidades</strong> llevan más de 10 días sin actividad.{" "}
            <a href="/pipeline" className="font-medium text-warning underline-offset-2 hover:underline">
              Ver oportunidades →
            </a>
          </div>
          <button
            onClick={() => setShowAlert(false)}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Cerrar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight">
            {getGreeting()}, {name} 👋
          </h1>
          <p className="text-sm text-muted-foreground capitalize mt-1">{today}</p>
        </div>
        <Button
          // FASE 2: conectar al copiloto IA (useCopilot.send(...))
          onClick={() => { /* TODO fase 2 */ }}
          className="bg-gradient-brand hover:opacity-90 text-primary-foreground shadow-glow gap-2"
        >
          <Sparkles className="h-4 w-4" />
          Resumen del día
        </Button>
      </div>

      {/* KPI Cards */}
      {kpisLoading && !kpis ? (
        <KpiCardsSkeleton />
      ) : (
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
      )}

      {/* Row: Run Rate + Rentabilidad */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <RunRateCard compact showSellers={canSeeTeam} />
        <ProfitabilityCard />
      </div>

      {/* Row: Mis Tareas */}
      <TaskCards />

      {/* Row 2: Actividad (2/3) + Briefing IA (1/3) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-xl border border-border bg-card shadow-card">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <h3 className="font-semibold">Actividad Reciente</h3>
            <p className="text-xs text-muted-foreground">Últimas acciones de tu equipo</p>
          </div>
          <Button variant="ghost" size="sm" className="text-primary">Ver todo</Button>
        </div>
        <div className="divide-y divide-border">
          {activityLoading && activity.length === 0 ? (
            <ListRowsSkeleton rows={5} />
          ) : (
            <>
            {activity.map((a) => {
            const meta = activityIcon[a.type] ?? activityIcon.note;
            const ActIcon = meta.icon;
            return (
              <div key={a.id} className="flex items-center gap-3 px-5 py-3 hover:bg-muted/50 transition-colors">
                <Avatar className="h-9 w-9">
                  <AvatarFallback className="bg-gradient-brand text-primary-foreground text-xs font-semibold">
                    {a.contactName ? a.contactName.split(" ").map(s => s[0]).slice(0, 2).join("") : "•"}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0 text-sm">
                  <p className="truncate">
                    <span className="text-muted-foreground">{a.description}</span>
                    {a.contactName && (
                      <>
                        {" · "}
                        {a.contactId ? (
                          <Link to={`/contacts/${a.contactId}`} className="font-medium text-foreground hover:text-primary">
                            {a.contactName}
                          </Link>
                        ) : <span className="font-medium text-foreground">{a.contactName}</span>}
                      </>
                    )}
                  </p>
                  <div className="flex items-center gap-1 text-[11px] text-muted-foreground mt-0.5">
                    <Clock className="h-3 w-3" /> {relativeTime(a.occurredAt)}
                  </div>
                </div>
                <div className={cn("h-7 w-7 grid place-items-center rounded-lg shrink-0", meta.color)}>
                  <ActIcon className="h-3.5 w-3.5" />
                </div>
              </div>
            );
          })}
          {activity.length === 0 && (
            <div className="px-5 py-8 text-center text-sm text-muted-foreground">Sin actividad reciente.</div>
          )}
            </>
          )}
        </div>
        </div>

        {/* Briefing proactivo de IA (agent_suggestions) */}
        <ProactiveBriefing />
      </div>

      {/* Row: AI Patterns (Etapa 6.6.5) */}
      <AIPatternsCard />

      {/* Row: Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Pipeline by stage */}
        <div className="rounded-xl border border-border bg-card p-5 shadow-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold">Pipeline por Etapa</h3>
              <p className="text-xs text-muted-foreground">Valor MXN acumulado</p>
            </div>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={pipelineByStage} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis
                  dataKey="stage"
                  stroke="hsl(var(--muted-foreground))"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  interval={0}
                  angle={-15}
                  textAnchor="end"
                  height={60}
                />
                <YAxis
                  stroke="hsl(var(--muted-foreground))"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  cursor={{ fill: "hsl(var(--muted))" }}
                  contentStyle={{
                    background: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                  formatter={(v: number) => [formatMXN(v), "Valor"]}
                />
                <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                  {pipelineByStage.map((_, i) => (
                    <Cell key={i} fill={stageColors[i % stageColors.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Oportunidades cerradas timeline */}
        <div className="rounded-xl border border-border bg-card p-5 shadow-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold">Oportunidades cerradas</h3>
              <p className="text-xs text-muted-foreground">Últimos 30 días</p>
            </div>
            <span className="text-xs font-semibold text-success inline-flex items-center gap-0.5">
              <ArrowUpRight className="h-3 w-3" /> +18%
            </span>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={dealsTimeline} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="gClosed" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--accent))" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis
                  dataKey="day"
                  stroke="hsl(var(--muted-foreground))"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  interval={4}
                />
                <YAxis
                  stroke="hsl(var(--muted-foreground))"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                  formatter={(v: number) => [formatMXN(v), "Cerrado"]}
                  labelFormatter={(l) => `Día ${l}`}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="hsl(var(--accent))"
                  strokeWidth={2.5}
                  fill="url(#gClosed)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
