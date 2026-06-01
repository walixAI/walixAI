import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { es } from "date-fns/locale";
import {
  BarChart3,
  MessageCircle,
  ChevronLeft,
  Users,
  TrendingDown,
  DollarSign,
  Bot,
  CheckCircle2,
  XCircle,
  Eye,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  api,
  startImpersonation,
  type PlatformTenantItem,
} from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { Logo } from "@/components/walix/Logo";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

// ── Plan styling ──────────────────────────────────────────────────────────────

const PLAN_STYLE: Record<string, string> = {
  starter: "bg-muted text-muted-foreground border-border",
  growth: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  business: "bg-violet-500/10 text-violet-600 border-violet-500/20",
  enterprise: "bg-amber-500/10 text-amber-600 border-amber-500/20",
};

function PlanBadge({ plan }: { plan: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold border capitalize",
        PLAN_STYLE[plan] ?? "bg-muted text-muted-foreground border-border",
      )}
    >
      {plan}
    </span>
  );
}

// ── Role Selector ─────────────────────────────────────────────────────────────

function RoleSelector({
  userName,
  onPlatform,
  onCRM,
}: {
  userName: string;
  onPlatform: () => void;
  onCRM: () => void;
}) {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-lg space-y-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <Logo />
          <div>
            <p className="text-sm text-muted-foreground">
              Bienvenido, <span className="font-medium text-foreground">{userName.split(" ")[0]}</span>
            </p>
            <h1 className="text-2xl font-bold tracking-tight mt-1">¿A dónde quieres ir?</h1>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {/* Gestionar Walix */}
          <button
            onClick={onPlatform}
            className="group flex flex-col items-start gap-3 rounded-2xl border border-border
                       bg-card p-6 text-left transition-all duration-150
                       hover:border-primary hover:shadow-lg hover:shadow-primary/10"
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-xl
                            bg-primary/10 text-primary group-hover:bg-primary group-hover:text-primary-foreground
                            transition-colors">
              <BarChart3 className="h-5 w-5" />
            </div>
            <div>
              <p className="font-semibold text-sm">Gestionar Walix</p>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                Métricas, tenants y costos de plataforma
              </p>
            </div>
          </button>

          {/* Mi CRM */}
          <button
            onClick={onCRM}
            className="group flex flex-col items-start gap-3 rounded-2xl border border-border
                       bg-card p-6 text-left transition-all duration-150
                       hover:border-primary hover:shadow-lg hover:shadow-primary/10"
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-xl
                            bg-muted text-muted-foreground group-hover:bg-primary group-hover:text-primary-foreground
                            transition-colors">
              <MessageCircle className="h-5 w-5" />
            </div>
            <div>
              <p className="font-semibold text-sm">Mi CRM</p>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                Dashboard normal de cliente
              </p>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

// ── KPI card ──────────────────────────────────────────────────────────────────

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  iconColor,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  iconColor: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", iconColor)}>
          <Icon className="h-4 w-4" />
        </div>
        <span className="text-xs text-muted-foreground font-medium">{label}</span>
      </div>
      <div>
        <p className="text-2xl font-bold tabular-nums">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ── Tenant row action ─────────────────────────────────────────────────────────

function ImpersonateButton({
  tenant,
  allTenants,
}: {
  tenant: PlatformTenantItem;
  allTenants: PlatformTenantItem[];
}) {
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: () => api.impersonateTenant(tenant.id),
    onSuccess: (data) => {
      const tenantName = allTenants.find((t) => t.id === tenant.id)?.name ?? tenant.id;
      startImpersonation(data.access_token, tenantName);
      navigate("/dashboard");
    },
    onError: (e: Error) => toast.error("Error al acceder", { description: e.message }),
  });

  return (
    <Button
      size="sm"
      variant="outline"
      className="h-7 text-xs gap-1.5"
      onClick={(e) => {
        e.stopPropagation();
        mutation.mutate();
      }}
      disabled={mutation.isPending}
    >
      {mutation.isPending ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <Eye className="h-3 w-3" />
      )}
      Ver cuenta
    </Button>
  );
}

// ── Main platform dashboard ───────────────────────────────────────────────────

function MainPlatformView({ onBack }: { onBack: () => void }) {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["platform-stats"],
    queryFn: () => api.getPlatformStats(),
    staleTime: 2 * 60_000,
  });

  const { data: tenants = [], isLoading: tenantsLoading } = useQuery({
    queryKey: ["platform-tenants"],
    queryFn: () => api.getPlatformTenants(),
    staleTime: 2 * 60_000,
  });

  const churnPct =
    stats && stats.active_tenants > 0
      ? ((stats.churned_this_month / stats.active_tenants) * 100).toFixed(1)
      : "0";

  // MRR breakdown string  e.g. "2 starter · 1 growth"
  const mrrBreakdown = stats
    ? Object.entries(stats.mrr_by_plan)
        .filter(([, v]) => v > 0)
        .map(([plan, usd]) => `${plan} $${usd}`)
        .join(" · ")
    : "";

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-background/80 backdrop-blur border-b border-border
                          px-6 h-14 flex items-center gap-3 shrink-0">
        <button
          onClick={onBack}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground
                     hover:bg-muted transition-colors"
          aria-label="Volver al selector"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>

        <div className="flex items-center gap-2">
          <h1 className="text-sm font-semibold">Walix Platform</h1>
          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold
                           bg-violet-500/15 text-violet-600 border border-violet-500/25">
            Platform Owner
          </span>
        </div>
      </header>

      <div className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-6 space-y-8">

        {/* ── KPI cards ───────────────────────────────────────────────────── */}
        <section>
          {statsLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="rounded-xl border border-border bg-card p-4 space-y-3">
                  <Skeleton className="h-8 w-8 rounded-lg" />
                  <Skeleton className="h-6 w-24" />
                  <Skeleton className="h-3 w-32" />
                </div>
              ))}
            </div>
          ) : stats ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KpiCard
                icon={DollarSign}
                label="MRR Total"
                value={`$${stats.total_mrr.toLocaleString("en-US")}`}
                sub={mrrBreakdown || "Sin suscripciones activas"}
                iconColor="bg-emerald-500/10 text-emerald-600"
              />
              <KpiCard
                icon={Users}
                label="Tenants activos"
                value={String(stats.active_tenants)}
                sub={`${stats.trials} trials · ${stats.total_tenants} total`}
                iconColor="bg-primary/10 text-primary"
              />
              <KpiCard
                icon={TrendingDown}
                label="Churn este mes"
                value={String(stats.churned_this_month)}
                sub={`${churnPct}% sobre activos`}
                iconColor="bg-destructive/10 text-destructive"
              />
              <KpiCard
                icon={Bot}
                label="Costo IA este mes"
                value={`$${stats.ai_costs_this_month.toFixed(2)}`}
                sub="USD · Haiku + Sonnet"
                iconColor="bg-violet-500/10 text-violet-600"
              />
            </div>
          ) : null}
        </section>

        {/* ── Tenants table ────────────────────────────────────────────────── */}
        <section className="space-y-3">
          <h2 className="text-base font-semibold">Tenants</h2>

          {tenantsLoading ? (
            <div className="rounded-xl border border-border overflow-hidden">
              {[1, 2, 3].map((i) => (
                <div key={i} className="px-4 py-3 border-b border-border last:border-0 flex gap-4">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-4 w-20 ml-auto" />
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-border overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    {["Nombre", "Plan", "Activo", "Leads", "Costo IA", "Creado", ""].map(
                      (col) => (
                        <th
                          key={col}
                          className="text-left text-xs font-semibold text-muted-foreground px-4 py-2.5 whitespace-nowrap"
                        >
                          {col}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {tenants.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="text-center py-10 text-sm text-muted-foreground">
                        Sin tenants registrados.
                      </td>
                    </tr>
                  ) : (
                    tenants.map((t) => (
                      <tr
                        key={t.id}
                        className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors"
                      >
                        <td className="px-4 py-3 font-medium whitespace-nowrap">{t.name}</td>
                        <td className="px-4 py-3">
                          <PlanBadge plan={t.plan} />
                        </td>
                        <td className="px-4 py-3">
                          {t.is_active ? (
                            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                          ) : (
                            <XCircle className="h-4 w-4 text-muted-foreground" />
                          )}
                        </td>
                        <td className="px-4 py-3 tabular-nums text-muted-foreground">
                          {t.leads_count.toLocaleString("en-US")}
                        </td>
                        <td className="px-4 py-3 tabular-nums text-muted-foreground">
                          ${t.ai_cost_this_month.toFixed(4)}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                          {format(parseISO(t.created_at), "d MMM yyyy", { locale: es })}
                        </td>
                        <td className="px-4 py-3">
                          <ImpersonateButton tenant={t} allTenants={tenants} />
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Renovaciones próximas ────────────────────────────────────────── */}
        {!statsLoading && stats && stats.renewals_next_30_days.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-base font-semibold">Renovaciones próximas (30 días)</h2>
            <div className="rounded-xl border border-border divide-y divide-border">
              {stats.renewals_next_30_days.map((r, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{r.tenant_name}</p>
                  </div>
                  <PlanBadge plan={r.plan} />
                  <p className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
                    {format(parseISO(r.renewal_date), "d MMM", { locale: es })}
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

// ── Page entry point ──────────────────────────────────────────────────────────

export default function PlatformDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [view, setView] = useState<"selector" | "main">("selector");

  return view === "selector" ? (
    <RoleSelector
      userName={user?.name ?? ""}
      onPlatform={() => setView("main")}
      onCRM={() => navigate("/dashboard")}
    />
  ) : (
    <MainPlatformView onBack={() => setView("selector")} />
  );
}
