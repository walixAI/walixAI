import { useState } from "react";
import { RefreshCw, AlertTriangle, TrendingUp, Calendar, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  usePipelineIntelligence,
  useRefreshIntelligence,
  type HealthSignal,
  type Risk,
} from "@/lib/queries/pipelineIntelligence";

// ── Health score circular SVG ─────────────────────────────────────────────────

const RADIUS = 36;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function ScoreCircle({ score, status }: { score: number; status: string }) {
  const offset = CIRCUMFERENCE - (score / 100) * CIRCUMFERENCE;
  const colorMap: Record<string, string> = {
    excellent: "stroke-success",
    good: "stroke-primary",
    warning: "stroke-warning",
    critical: "stroke-danger",
  };
  const stroke = colorMap[status] ?? "stroke-primary";
  return (
    <div className="relative flex items-center justify-center">
      <svg width="96" height="96" viewBox="0 0 96 96" className="-rotate-90">
        <circle cx="48" cy="48" r={RADIUS} strokeWidth="8" className="stroke-muted fill-none" />
        <circle
          cx="48" cy="48" r={RADIUS}
          strokeWidth="8"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          className={cn("transition-all duration-700", stroke)}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-2xl font-bold leading-none">{score}</span>
        <span className="text-[10px] text-muted-foreground uppercase tracking-wide">/ 100</span>
      </div>
    </div>
  );
}

// ── Tone badge ────────────────────────────────────────────────────────────────

const TONE_STYLE: Record<string, string> = {
  positive: "bg-success/10 text-success",
  negative: "bg-danger/10 text-danger",
  neutral:  "bg-muted text-muted-foreground",
};

function SignalRow({ signal }: { signal: HealthSignal }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs py-1">
      <span className="text-muted-foreground">{signal.label}</span>
      <span className={cn("rounded-full px-2 py-0.5 font-medium shrink-0", TONE_STYLE[signal.tone] ?? TONE_STYLE.neutral)}>
        {signal.value}
      </span>
    </div>
  );
}

// ── Severity badge ────────────────────────────────────────────────────────────

const SEV_STYLE: Record<string, string> = {
  high:   "bg-danger/10 text-danger",
  medium: "bg-warning/10 text-warning",
  low:    "bg-muted text-muted-foreground",
};

const SEV_LABEL: Record<string, string> = {
  high: "Alta", medium: "Media", low: "Baja",
};

function RiskRow({ risk }: { risk: Risk }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-border last:border-0">
      <span className={cn("mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold", SEV_STYLE[risk.severity] ?? SEV_STYLE.medium)}>
        {SEV_LABEL[risk.severity] ?? risk.severity}
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium leading-tight">{risk.title}</p>
        <p className="text-xs text-muted-foreground leading-snug mt-0.5">{risk.detail}</p>
      </div>
    </div>
  );
}

// ── Main widget ───────────────────────────────────────────────────────────────

function fmtMXN(n: number) {
  return n.toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-MX", { day: "numeric", month: "short" });
}

export function AiIntelligenceSection() {
  const { data, isLoading } = usePipelineIntelligence();
  const refresh = useRefreshIntelligence();
  const [refreshing, setRefreshing] = useState(false);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await refresh();
    } finally {
      setRefreshing(false);
    }
  }

  if (isLoading || !data) {
    return (
      <div className="rounded-xl border border-border bg-card p-5 shadow-card">
        <div className="h-6 w-40 rounded bg-muted animate-pulse mb-4" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-48 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const { pipeline_health, closing_soon, risks, executive_summary, source } = data;

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 grid place-items-center rounded-lg bg-primary/10 text-primary">
            <Zap className="h-4 w-4" />
          </div>
          <h3 className="text-sm font-semibold">Inteligencia IA</h3>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5 text-xs text-muted-foreground h-7"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
          Regenerar
        </Button>
      </div>

      {/* Fallback notice */}
      {source === "fallback" && (
        <div className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          Mostrando datos de demostración: el servicio IA no respondió
        </div>
      )}

      {/* Grid: 3 cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 1. Pipeline health */}
        <div className="rounded-xl border border-border bg-background p-4 flex flex-col items-center gap-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Salud del Pipeline</p>
          <ScoreCircle score={pipeline_health.score} status={pipeline_health.status} />
          <div className="w-full divide-y divide-border">
            {pipeline_health.signals.map((sig) => (
              <SignalRow key={sig.label} signal={sig} />
            ))}
          </div>
        </div>

        {/* 2. Closing soon */}
        <div className="rounded-xl border border-border bg-background p-4 flex flex-col gap-2">
          <div className="flex items-center gap-2 mb-1">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Próximas a cerrar</p>
          </div>
          {closing_soon.length === 0 ? (
            <p className="text-xs text-muted-foreground py-4 text-center">Sin deals en etapa pre-cierre</p>
          ) : (
            <div className="space-y-1.5 overflow-y-auto max-h-52">
              {closing_soon.map((deal) => (
                <div key={deal.id} className="flex items-center justify-between gap-2 rounded-lg border border-border px-2.5 py-2">
                  <div className="min-w-0">
                    <p className="text-xs font-medium truncate">{deal.name}</p>
                    <p className="text-[10px] text-muted-foreground truncate">{deal.stage_name}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-xs font-semibold">{fmtMXN(deal.amount)}</p>
                    <p className="text-[10px] text-muted-foreground">{fmtDate(deal.expected_close_date)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 3. Risks */}
        <div className="rounded-xl border border-border bg-background p-4 flex flex-col gap-1">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground" />
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Riesgos esta semana</p>
          </div>
          {risks.length === 0 ? (
            <p className="text-xs text-muted-foreground py-4 text-center flex items-center justify-center gap-1.5">
              <TrendingUp className="h-3.5 w-3.5 text-success" />
              Sin riesgos identificados
            </p>
          ) : (
            <div className="divide-y divide-border">
              {risks.map((risk, i) => (
                <RiskRow key={i} risk={risk} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Executive summary — full width */}
      <div className="rounded-xl border border-border bg-muted/30 px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Resumen ejecutivo</p>
        <p className="text-sm text-foreground leading-relaxed">{executive_summary}</p>
      </div>
    </div>
  );
}
