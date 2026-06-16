import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BarChart2, Users, CheckCircle2, Clock, DollarSign,
  AlertTriangle, Zap, Download, ChevronRight,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { api } from "@/lib/api";
import type { ROIOut } from "@/lib/api";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";

// ── CSV export ────────────────────────────────────────────────────────────────

function generateROICSV(data: ROIOut, period: number): string {
  const rows: string[][] = [
    ["Campo", "Valor"],
    ["Período", data.period_label],
    ["Pacientes captados", String(data.leads_total)],
    ["Calificados por el bot", String(data.bot_qualified)],
    ["Tasa de calificación (%)", String(data.bot_qualification_rate)],
    ["Convertidos", String(data.converted)],
    ["Tasa de conversión (%)", String(data.conversion_rate)],
    ["Mensajes enviados por bot", String(data.bot_messages_sent)],
    ["Minutos ahorrados (estimado)", String(data.estimated_minutes_saved)],
    ["Horas ahorradas (estimado)", String(data.estimated_hours_saved)],
    ...(data.estimated_revenue != null
      ? [["Revenue estimado (MXN)", String(data.estimated_revenue)]]
      : []),
    ["Tiempo prom. respuesta (min)", data.avg_response_time_minutes != null ? String(data.avg_response_time_minutes) : "—"],
    ["Sugerencias IA aceptadas (%)", String(data.agent_acceptance_rate)],
  ];
  return rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
}

function downloadFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Period selector ───────────────────────────────────────────────────────────

const PERIODS = [
  { label: "7 días",  value: 7 },
  { label: "30 días", value: 30 },
  { label: "90 días", value: 90 },
] as const;

// ── Sentiment colors ──────────────────────────────────────────────────────────

const SENTIMENT_CONFIG: Record<string, { label: string; color: string; emoji: string }> = {
  interesado: { label: "Interesado", color: "text-success bg-success/10",     emoji: "😊" },
  urgente:    { label: "Urgente",    color: "text-warning bg-warning/10",     emoji: "⚡" },
  neutral:    { label: "Neutral",    color: "text-muted-foreground bg-muted", emoji: "😐" },
  negativo:   { label: "Negativo",   color: "text-danger bg-danger/10",       emoji: "😞" },
};

const SOURCE_LABELS: Record<string, string> = {
  whatsapp_inbound: "WhatsApp",
  meta_ads:         "Meta Ads",
  manual:           "Manual",
};

// ── Revenue config modal ──────────────────────────────────────────────────────

function RevenueConfigModal({
  open,
  current,
  onClose,
}: {
  open: boolean;
  current: number | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [value, setValue] = useState(current != null ? String(current) : "");

  const mutation = useMutation({
    mutationFn: (v: number) => api.updateRoiConfig(v),
    onSuccess: () => {
      toast({ description: "Configuración guardada." });
      qc.invalidateQueries({ queryKey: ["roi"] });
      onClose();
    },
    onError: () => toast({ description: "Error al guardar.", variant: "destructive" }),
  });

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Valor por conversión</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          ¿Cuánto vale en promedio una cita o consulta para tu clínica?
        </p>
        <div className="flex items-center gap-2 mt-2">
          <span className="text-sm font-medium text-muted-foreground">MXN $</span>
          <Input
            type="number"
            placeholder="850"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            min={0}
          />
        </div>
        <Button
          className="w-full mt-2"
          disabled={!value || isNaN(Number(value)) || mutation.isPending}
          onClick={() => mutation.mutate(Number(value))}
        >
          {mutation.isPending ? "Guardando..." : "Guardar y calcular ROI"}
        </Button>
      </DialogContent>
    </Dialog>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ROIDashboard() {
  const [period, setPeriod] = useState<7 | 30 | 90>(30);
  const [revenueModalOpen, setRevenueModalOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["roi", period],
    queryFn: () => api.getRoi(period),
    staleTime: 60_000,
  });

  const handleExport = () => {
    if (!data) return;
    const csv = generateROICSV(data, period);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const date = new Date().toISOString().slice(0, 10);
    downloadFile(blob, `walix-roi-${period}d-${date}.csv`);
  };

  const today = new Date().toLocaleDateString("es-MX", {
    day: "numeric", month: "long", year: "numeric",
  });

  // Source bar data
  const sourceData = data
    ? Object.entries(data.leads_by_source).map(([key, count]) => ({
        name: SOURCE_LABELS[key] ?? key,
        count,
        pct: data.leads_total > 0 ? Math.round((count / data.leads_total) * 100) : 0,
      }))
    : [];

  return (
    <div className="space-y-6 max-w-[1400px]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-0.5">
            <BarChart2 className="h-5 w-5 text-primary" />
            <h1 className="text-2xl font-bold tracking-tight">
              ROI {data ? `— ${data.period_label}` : ""}
            </h1>
          </div>
          <p className="text-sm text-muted-foreground">Actualizado: {today}</p>
        </div>

        {/* Period tabs */}
        <div className="flex items-center bg-muted rounded-lg p-1 gap-0.5">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value as 7 | 30 | 90)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                period === p.value
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <Button variant="outline" size="sm" onClick={handleExport} disabled={!data} className="gap-1.5">
          <Download className="h-3.5 w-3.5" />
          Exportar
        </Button>
      </div>

      {/* ROW 1 — KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Pacientes captados"
          value={isLoading ? "—" : (data?.leads_total ?? 0)}
          format="number"
          icon={<Users className="h-4 w-4" />}
        />
        <KpiCard
          label={`Convirtieron (${isLoading ? "—" : (data?.conversion_rate ?? 0).toFixed(1)}%)`}
          value={isLoading ? "—" : (data?.converted ?? 0)}
          format="number"
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
        <KpiCard
          label="Horas ahorradas por el bot"
          value={isLoading ? "—" : (data?.estimated_hours_saved ?? 0)}
          format="number"
          icon={<Clock className="h-4 w-4" />}
        />
        {data?.estimated_revenue != null ? (
          <KpiCard
            label="Revenue generado (MXN)"
            value={data.estimated_revenue}
            format="currency"
            icon={<DollarSign className="h-4 w-4" />}
          />
        ) : (
          <div className="rounded-xl border border-dashed border-border bg-card p-5 flex flex-col justify-between">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Revenue generado
            </p>
            <p className="text-sm text-muted-foreground mt-2">Sin configurar</p>
            <button
              onClick={() => setRevenueModalOpen(true)}
              className="mt-3 text-xs text-primary font-semibold flex items-center gap-1 hover:underline w-fit"
            >
              Configurar valor <ChevronRight className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>

      {/* ROW 2 — Funnel + Origen */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Funnel del bot */}
        <div className="rounded-xl border border-border bg-card shadow-card p-5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">
            Funnel del bot
          </p>
          {!isLoading && data && (
            <div className="space-y-3">
              <FunnelBar
                label="Leads captados"
                count={data.leads_total}
                total={data.leads_total}
                color="bg-primary"
              />
              <FunnelBar
                label={`Calificados por IA (≥60 pts)`}
                count={data.bot_qualified}
                total={data.leads_total}
                color="bg-accent"
                pctLabel={`${data.bot_qualification_rate}%`}
              />
              <FunnelBar
                label="Convertidos"
                count={data.converted}
                total={data.leads_total}
                color="bg-success"
                pctLabel={`${data.conversion_rate}%`}
              />
            </div>
          )}
          {isLoading && <div className="h-24 animate-pulse bg-muted rounded-lg" />}
        </div>

        {/* Origen de pacientes */}
        <div className="rounded-xl border border-border bg-card shadow-card p-5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">
            Origen de pacientes
          </p>
          {!isLoading && sourceData.length > 0 ? (
            <ResponsiveContainer width="100%" height={140}>
              <BarChart
                data={sourceData}
                layout="vertical"
                margin={{ top: 0, right: 40, left: 0, bottom: 0 }}
              >
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 12 }} />
                <Tooltip
                  formatter={(v: number, _n: string, props: { payload?: { pct?: number } }) =>
                    [`${v} (${props?.payload?.pct ?? 0}%)`, "Pacientes"]
                  }
                  contentStyle={{ fontSize: 12 }}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {sourceData.map((_, i) => (
                    <Cell
                      key={i}
                      fill={["hsl(var(--primary))", "hsl(var(--accent))", "hsl(var(--muted-foreground))"][i % 3]}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            !isLoading && (
              <p className="text-sm text-muted-foreground">Sin datos de origen disponibles</p>
            )
          )}
          {isLoading && <div className="h-24 animate-pulse bg-muted rounded-lg" />}
        </div>
      </div>

      {/* ROW 3 — Pipeline por etapa */}
      {data && data.pipeline_by_stage.length > 0 && (
        <div className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <p className="font-semibold text-sm">Pipeline por etapa</p>
            <p className="text-xs text-muted-foreground mt-0.5">{data.period_label}</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Etapa</th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Pacientes</th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Días prom. en etapa</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.pipeline_by_stage.map((stage) => (
                  <tr key={stage.stage_key ?? stage.stage_name} className="hover:bg-muted/30 transition-colors">
                    <td className="px-5 py-3 font-medium">{stage.stage_name}</td>
                    <td className="px-5 py-3 text-right tabular-nums">{stage.count}</td>
                    <td className="px-5 py-3 text-right text-muted-foreground">
                      {stage.avg_days_in_stage != null ? stage.avg_days_in_stage.toFixed(1) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ROW 4 — Sentimiento */}
      {data && Object.values(data.sentiment_breakdown).some((v) => v > 0) && (
        <div className="rounded-xl border border-border bg-card shadow-card p-5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">
            Sentimiento de pacientes
          </p>
          <div className="flex flex-wrap gap-3">
            {Object.entries(data.sentiment_breakdown).map(([key, count]) => {
              const cfg = SENTIMENT_CONFIG[key];
              if (!cfg || count === 0) return null;
              return (
                <span
                  key={key}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold ${cfg.color}`}
                >
                  {cfg.emoji} {cfg.label} <span className="font-bold">({count})</span>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* ROW 5 — Configuración de valor */}
      {data && data.revenue_per_conversion == null && (
        <div className="rounded-xl border-2 border-dashed border-primary/30 bg-primary/5 p-6">
          <div className="flex items-start gap-4">
            <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <DollarSign className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1">
              <p className="font-semibold text-foreground">¿Cuánto vale una cita para tu clínica?</p>
              <p className="text-sm text-muted-foreground mt-1">
                Configura el valor promedio de una conversión y Walix calculará automáticamente el revenue generado por el bot.
              </p>
              <Button
                size="sm"
                className="mt-4"
                onClick={() => setRevenueModalOpen(true)}
              >
                Configurar y calcular ROI
              </Button>
            </div>
          </div>
        </div>
      )}

      {data && data.revenue_per_conversion != null && (
        <div className="flex items-center justify-end">
          <button
            onClick={() => setRevenueModalOpen(true)}
            className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1 transition-colors"
          >
            Cambiar valor por conversión <ChevronRight className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* ROW 6 — Insights del equipo */}
      {data && (
        <div className="rounded-xl border border-border bg-card shadow-card p-5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">
            Insights del equipo
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Response time */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Tiempo promedio de respuesta</p>
              <div className="flex items-center gap-2">
                <p className="text-lg font-bold tabular-nums">
                  {data.avg_response_time_minutes != null
                    ? `${data.avg_response_time_minutes} min`
                    : "—"}
                </p>
                {data.avg_response_time_minutes != null && data.avg_response_time_minutes > 15 && (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-warning/10 text-warning flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" /> Oportunidad de mejora
                  </span>
                )}
              </div>
            </div>

            {/* AI suggestions */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Sugerencias de IA aceptadas</p>
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-primary shrink-0" />
                <p className="text-lg font-bold">
                  {data.agent_acceptance_rate}%
                </p>
                <span className="text-xs text-muted-foreground">
                  ({data.agent_suggestions_accepted}/{data.agent_suggestions_generated})
                </span>
              </div>
            </div>

            {/* Waiting leads */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Esperando respuesta ahora</p>
              <div className="flex items-center gap-2">
                <p className={`text-lg font-bold ${data.leads_waiting_response > 0 ? "text-danger" : "text-success"}`}>
                  {data.leads_waiting_response}
                </p>
                <span className="text-xs text-muted-foreground">
                  {data.leads_waiting_response === 1 ? "paciente" : "pacientes"} &gt; 60 min sin respuesta
                </span>
                {data.leads_waiting_response > 0 && (
                  <AlertTriangle className="h-3.5 w-3.5 text-danger" />
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Revenue config modal */}
      <RevenueConfigModal
        open={revenueModalOpen}
        current={data?.revenue_per_conversion ?? null}
        onClose={() => setRevenueModalOpen(false)}
      />
    </div>
  );
}

// ── Funnel bar component ──────────────────────────────────────────────────────

function FunnelBar({
  label,
  count,
  total,
  color,
  pctLabel,
}: {
  label: string;
  count: number;
  total: number;
  color: string;
  pctLabel?: string;
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm text-foreground">{label}</p>
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold tabular-nums">{count}</span>
          {pctLabel && (
            <span className="text-xs text-muted-foreground">({pctLabel})</span>
          )}
        </div>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
