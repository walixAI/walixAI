import { useState, useEffect } from "react";
import { Edit2, Save, Loader2, Sparkles, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  api,
  type OppDetailRead,
  type OppActivityOut,
  type OppHistoryOut,
  type TeamMemberOut,
  type OppNextStepOut,
  type OppProbabilityOut,
} from "@/lib/api";
import { useOpportunityStore, oppReadToCard } from "../opportunityStore";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";
import { es } from "date-fns/locale";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatMXN(n: string | number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const val = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(val)) return "—";
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function relativeTime(iso: string): string {
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: es });
  } catch {
    return iso;
  }
}

const ACTIVITY_ICON: Record<string, string> = {
  created: "🌱",
  stage_change: "➡️",
  note: "📝",
  task: "✅",
  message: "💬",
  ai_suggestion: "✨",
  won: "🏆",
  lost: "❌",
};

const SOURCE_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp",
  web_form: "Formulario web",
  referral: "Referido",
  manual: "Manual",
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function ProbBar({ value }: { value: number }) {
  const colorClass = value >= 70 ? "bg-success" : value >= 40 ? "bg-warning" : "bg-danger";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full rounded-full", colorClass)} style={{ width: `${value}%` }} />
      </div>
      <span className={cn("text-xs font-semibold tabular-nums w-8 text-right", {
        "text-success": value >= 70,
        "text-warning": value >= 40 && value < 70,
        "text-danger": value < 40,
      })}>{value}%</span>
    </div>
  );
}

// ── Resumen tab ───────────────────────────────────────────────────────────────

function ResumenTab({ opp, onUpdated }: { opp: OppDetailRead; onUpdated: (o: import("@/lib/api").OppRead) => void }) {
  const { stages, branchId } = useOpportunityStore();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [team, setTeam] = useState<TeamMemberOut[]>([]);
  const [form, setForm] = useState({
    title: opp.title,
    amount: opp.amount ?? "",
    probability: opp.probability ?? 50,
    stage_id: opp.stage?.id ?? "",
    close_date: opp.close_date ?? "",
    source: opp.source ?? "",
    notes: opp.notes ?? "",
    assigned_to: opp.assigned_to ?? "",
  });

  useEffect(() => {
    api.getTeam(branchId ?? "").then(setTeam).catch(() => {});
  }, [branchId]);

  // Sync form when opp changes
  useEffect(() => {
    setForm({
      title: opp.title,
      amount: opp.amount ?? "",
      probability: opp.probability ?? 50,
      stage_id: opp.stage?.id ?? "",
      close_date: opp.close_date ?? "",
      source: opp.source ?? "",
      notes: opp.notes ?? "",
      assigned_to: opp.assigned_to ?? "",
    });
    setEditing(false);
  }, [opp.id]);

  async function handleSave() {
    setSaving(true);
    try {
      const updated = await api.updateOpportunity(opp.id, {
        title: form.title || undefined,
        amount: form.amount || undefined,
        probability: form.probability,
        stage_id: form.stage_id || undefined,
        close_date: form.close_date || undefined,
        source: form.source || undefined,
        notes: form.notes || undefined,
        assigned_to: form.assigned_to || undefined,
      });
      onUpdated(updated);
      setEditing(false);
      toast.success("Oportunidad actualizada");
    } catch (e) {
      toast.error("Error al guardar", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  }

  const stageObj = opp.stage;

  return (
    <div className="space-y-4">
      {/* Edit / Save toggle */}
      <div className="flex justify-end">
        {editing ? (
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)} disabled={saving}>
              Cancelar
            </Button>
            <Button size="sm" onClick={handleSave} disabled={saving} className="gap-1.5">
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Save className="h-3.5 w-3.5" aria-hidden="true" />}
              Guardar
            </Button>
          </div>
        ) : (
          <Button variant="outline" size="sm" onClick={() => setEditing(true)} className="gap-1.5">
            <Edit2 className="h-3.5 w-3.5" aria-hidden="true" />
            Editar
          </Button>
        )}
      </div>

      {editing ? (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Título *</Label>
            <Input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              className="h-9"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Monto (MXN)</Label>
            <Input
              type="number"
              min={0}
              value={form.amount}
              onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
              className="h-9"
              placeholder="0"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Probabilidad: {form.probability}%</Label>
            <Slider
              min={0}
              max={100}
              step={5}
              value={[form.probability]}
              onValueChange={([v]) => setForm((f) => ({ ...f, probability: v }))}
              aria-label="Probabilidad de cierre"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Etapa</Label>
            <select
              value={form.stage_id}
              onChange={(e) => setForm((f) => ({ ...f, stage_id: e.target.value }))}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              aria-label="Seleccionar etapa"
            >
              <option value="">Sin etapa</option>
              {stages.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Fecha de cierre</Label>
            <Input
              type="date"
              value={form.close_date}
              onChange={(e) => setForm((f) => ({ ...f, close_date: e.target.value }))}
              className="h-9"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Fuente</Label>
            <select
              value={form.source}
              onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              aria-label="Fuente de la oportunidad"
            >
              <option value="">Sin especificar</option>
              <option value="whatsapp">WhatsApp</option>
              <option value="web_form">Formulario web</option>
              <option value="referral">Referido</option>
              <option value="manual">Manual</option>
            </select>
          </div>
          {team.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-xs">Vendedor asignado</Label>
              <select
                value={form.assigned_to}
                onChange={(e) => setForm((f) => ({ ...f, assigned_to: e.target.value }))}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                aria-label="Vendedor asignado"
              >
                <option value="">Sin asignar</option>
                {team.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
          )}
          <div className="space-y-1.5">
            <Label className="text-xs">Notas</Label>
            <Textarea
              rows={3}
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              placeholder="Notas internas…"
              className="resize-none"
            />
          </div>
        </div>
      ) : (
        <dl className="space-y-3">
          <div>
            <dt className="text-xs text-muted-foreground">Monto</dt>
            <dd className="text-lg font-bold text-success tabular-nums">{formatMXN(opp.amount)}</dd>
          </div>
          {stageObj && (
            <div>
              <dt className="text-xs text-muted-foreground">Etapa</dt>
              <dd>
                <span
                  className={cn(
                    "inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full",
                    !stageObj.color && "bg-primary/10 text-primary border border-primary/25",
                  )}
                  style={stageObj.color ? {
                    backgroundColor: `${stageObj.color}20`,
                    color: stageObj.color,
                    border: `1px solid ${stageObj.color}40`,
                  } : undefined}
                >
                  {stageObj.name}
                </span>
              </dd>
            </div>
          )}
          {opp.probability != null && (
            <div>
              <dt className="text-xs text-muted-foreground mb-1">Probabilidad</dt>
              <ProbBar value={opp.probability} />
            </div>
          )}
          {opp.close_date && (
            <div>
              <dt className="text-xs text-muted-foreground">Fecha de cierre</dt>
              <dd className="text-sm">{new Date(opp.close_date + "T00:00:00").toLocaleDateString("es-MX", { day: "2-digit", month: "long", year: "numeric" })}</dd>
            </div>
          )}
          {opp.source && (
            <div>
              <dt className="text-xs text-muted-foreground">Fuente</dt>
              <dd className="text-sm">{SOURCE_LABELS[opp.source] ?? opp.source}</dd>
            </div>
          )}
          {opp.assigned_to_name && (
            <div>
              <dt className="text-xs text-muted-foreground">Vendedor</dt>
              <dd className="text-sm">{opp.assigned_to_name}</dd>
            </div>
          )}
          {opp.lead && (
            <div>
              <dt className="text-xs text-muted-foreground">Contacto</dt>
              <dd className="text-sm">{opp.lead.name ?? opp.lead.wa_phone ?? "—"}</dd>
            </div>
          )}
          {opp.notes && (
            <div>
              <dt className="text-xs text-muted-foreground">Notas</dt>
              <dd className="text-sm whitespace-pre-wrap text-muted-foreground">{opp.notes}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}

// ── Actividad tab ─────────────────────────────────────────────────────────────

function ActividadTab({ activities }: { activities: OppActivityOut[] }) {
  if (activities.length === 0)
    return <p className="text-sm text-muted-foreground text-center py-10">Sin actividad registrada</p>;
  return (
    <div className="relative pl-8">
      <div className="absolute left-3 top-0 bottom-0 w-px bg-border" aria-hidden="true" />
      <ul className="space-y-4">
        {activities.map((act) => (
          <li key={act.id} className="relative">
            <span
              className="absolute -left-[22px] top-1 h-3 w-3 rounded-full border-2 border-background bg-primary"
              aria-hidden="true"
            />
            <div>
              <p className="text-sm leading-snug">
                <span className="mr-1.5" aria-hidden="true">{ACTIVITY_ICON[act.type] ?? "•"}</span>
                {act.description ?? act.type}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{relativeTime(act.created_at)}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Historial tab ─────────────────────────────────────────────────────────────

function HistorialTab({ opp, history }: { opp: OppDetailRead; history: OppHistoryOut[] }) {
  const { stages } = useOpportunityStore();
  const stageNameMap = new Map(stages.map((s) => [s.id, s.name]));
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
        <p className="text-sm font-medium">
          <span className="tabular-nums font-bold">{opp.days_in_stage}</span>{" "}
          día{opp.days_in_stage !== 1 ? "s" : ""} en etapa actual
          {opp.stage && <span className="text-muted-foreground"> "{opp.stage.name}"</span>}
        </p>
      </div>
      {history.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-6">Sin cambios de etapa</p>
      ) : (
        <ul className="space-y-2">
          {history.map((h) => (
            <li key={h.id} className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground truncate max-w-[90px]">
                {stageNameMap.get(h.from_stage_id ?? "") ?? "(inicio)"}
              </span>
              <span className="text-muted-foreground" aria-hidden="true">→</span>
              <span className="font-medium truncate max-w-[90px]">
                {stageNameMap.get(h.to_stage_id) ?? h.to_stage_id.slice(0, 8)}
              </span>
              <span className="ml-auto text-[11px] text-muted-foreground shrink-0">
                {relativeTime(h.created_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── IA tab ─────────────────────────────────────────────────────────────────────

type AICardState = "idle" | "loading" | "result";

const URGENCY_STYLE: Record<string, string> = {
  high: "bg-danger/10 text-danger border border-danger/20",
  medium: "bg-warning/10 text-warning border border-warning/20",
  low: "bg-success/10 text-success border border-success/20",
};
const URGENCY_LABEL: Record<string, string> = {
  high: "Urgente",
  medium: "Medio",
  low: "Bajo",
};

function NextStepCard({ oppId }: { oppId: string }) {
  const [state, setState] = useState<AICardState>("idle");
  const [result, setResult] = useState<OppNextStepOut | null>(null);

  async function handleCalculate() {
    setState("loading");
    try {
      const data = await api.getOppNextStep(oppId);
      setResult(data);
      setState("result");
    } catch {
      toast.info("La IA no está disponible ahora");
      setState("idle");
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
        <p className="text-sm font-semibold flex-1">Siguiente paso sugerido</p>
        {state === "result" && (
          <button
            type="button"
            onClick={handleCalculate}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Recalcular siguiente paso"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
      </div>

      {state === "idle" && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Obtén una sugerencia IA para el siguiente paso con este contacto.
          </p>
          <Button size="sm" className="w-full gap-2" onClick={handleCalculate}>
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Calcular siguiente paso
          </Button>
        </div>
      )}

      {state === "loading" && (
        <div className="space-y-2" aria-busy="true" aria-label="Calculando siguiente paso">
          <Skeleton className="h-4 w-full rounded" />
          <Skeleton className="h-4 w-3/4 rounded" />
          <Skeleton className="h-3 w-1/2 rounded" />
        </div>
      )}

      {state === "result" && result && (
        <div className="space-y-2">
          {result.urgency && (
            <span
              className={cn(
                "inline-block text-[10px] font-bold px-1.5 py-0.5 rounded-full",
                URGENCY_STYLE[result.urgency] ?? URGENCY_STYLE.low,
              )}
            >
              {URGENCY_LABEL[result.urgency] ?? result.urgency}
            </span>
          )}
          {result.text ? (
            <p className="text-sm leading-relaxed">{result.text}</p>
          ) : (
            <p className="text-xs text-muted-foreground">Sin sugerencia disponible.</p>
          )}
          {result.reasoning && (
            <p className="text-xs text-muted-foreground leading-relaxed border-t border-border pt-2 mt-2">
              {result.reasoning}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ProbabilityCard({ oppId }: { oppId: string }) {
  const { drawerOpp, refreshBoardCard } = useOpportunityStore();
  const [state, setState] = useState<AICardState>("idle");
  const [result, setResult] = useState<OppProbabilityOut | null>(null);
  const [applying, setApplying] = useState(false);

  const currentProb = drawerOpp?.probability ?? null;

  async function handleCalculate() {
    setState("loading");
    try {
      const data = await api.getOppProbability(oppId);
      setResult(data);
      setState("result");
    } catch {
      toast.info("La IA no está disponible ahora");
      setState("idle");
    }
  }

  async function handleApply() {
    if (!result || !drawerOpp) return;
    setApplying(true);
    try {
      const updated = await api.updateOpportunity(oppId, { probability: result.suggested });
      refreshBoardCard(updated);
      useOpportunityStore.getState().fetchDrawerOpp(oppId);
      toast.success(`Probabilidad actualizada a ${result.suggested}%`);
    } catch {
      toast.error("Error al actualizar probabilidad");
    } finally {
      setApplying(false);
    }
  }

  const suggestedDiffers =
    result !== null && currentProb !== null && result.suggested !== currentProb;
  const suggestedDiffersFromNull = result !== null && currentProb === null;

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span aria-hidden="true">📊</span>
        <p className="text-sm font-semibold flex-1">Probabilidad de cierre</p>
        {state === "result" && (
          <button
            type="button"
            onClick={handleCalculate}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Recalcular probabilidad"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
      </div>

      {state === "idle" && (
        <div className="space-y-2">
          {currentProb !== null && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Actual:</span>
              <ProbBar value={currentProb} />
            </div>
          )}
          <Button size="sm" className="w-full gap-2" onClick={handleCalculate}>
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Auto-calcular
          </Button>
        </div>
      )}

      {state === "loading" && (
        <div className="space-y-2" aria-busy="true" aria-label="Calculando probabilidad">
          <Skeleton className="h-4 w-full rounded" />
          <Skeleton className="h-4 w-3/4 rounded" />
        </div>
      )}

      {state === "result" && result && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            {currentProb !== null && (
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">Actual</p>
                <ProbBar value={currentProb} />
              </div>
            )}
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">Sugerida IA</p>
              <ProbBar value={result.suggested} />
            </div>
          </div>

          {result.signals.length > 0 && (
            <ul className="space-y-1">
              {result.signals.map((sig, i) => (
                <li key={i} className="text-xs text-muted-foreground flex gap-1.5">
                  <span className="text-primary shrink-0" aria-hidden="true">•</span>
                  {sig}
                </li>
              ))}
            </ul>
          )}

          {(suggestedDiffers || suggestedDiffersFromNull) && (
            <Button
              size="sm"
              className="w-full"
              onClick={handleApply}
              disabled={applying}
            >
              {applying ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" aria-hidden="true" />
              ) : null}
              Aplicar {result.suggested}%
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function IATab({ oppId }: { oppId: string | null }) {
  return (
    <div className="space-y-3">
      {oppId ? (
        <>
          <NextStepCard oppId={oppId} />
          <ProbabilityCard oppId={oppId} />
        </>
      ) : (
        <p className="text-sm text-muted-foreground text-center py-6">
          Selecciona una oportunidad para ver los análisis IA.
        </p>
      )}
      <div className="rounded-xl border border-border bg-card p-4 space-y-2 opacity-60">
        <div className="flex items-center gap-2">
          <span aria-hidden="true">📄</span>
          <p className="text-sm font-semibold flex-1">Generar propuesta PDF</p>
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
            Pro
          </span>
        </div>
        <p className="text-xs text-muted-foreground">Disponible en plan Pro.</p>
      </div>
    </div>
  );
}

// ── Main Drawer ────────────────────────────────────────────────────────────────

export function OpportunityDrawer() {
  const { drawerOpen, drawerOpp, drawerLoading, closeDrawer, refreshBoardCard } = useOpportunityStore();

  function handleUpdated(opp: import("@/lib/api").OppRead) {
    refreshBoardCard(opp);
    // Re-fetch drawer to get updated activities
    if (drawerOpp) {
      useOpportunityStore.getState().fetchDrawerOpp(opp.id);
    }
  }

  return (
    <Sheet open={drawerOpen} onOpenChange={(o) => { if (!o) closeDrawer(); }}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-[480px] flex flex-col p-0 gap-0 overflow-hidden"
      >
        {drawerLoading || !drawerOpp ? (
          <div className="p-6 space-y-4" aria-busy="true" aria-label="Cargando detalle">
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-32 w-full rounded-xl" />
            <Skeleton className="h-20 w-full rounded-xl" />
          </div>
        ) : (
          <>
            <SheetHeader className="px-6 pt-6 pb-4 border-b border-border space-y-2 shrink-0">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-base font-bold leading-snug line-clamp-2">
                    {drawerOpp.title}
                  </SheetTitle>
                  {drawerOpp.amount && (
                    <p className="text-lg font-bold text-success tabular-nums mt-0.5">
                      {formatMXN(drawerOpp.amount)}
                    </p>
                  )}
                </div>
                {drawerOpp.stage && (
                  <span
                    className={cn(
                      "inline-flex items-center text-xs font-medium px-2 py-1 rounded-full shrink-0 mt-0.5",
                      !drawerOpp.stage.color && "bg-primary/10 text-primary border border-primary/25",
                    )}
                    style={drawerOpp.stage.color ? {
                      backgroundColor: `${drawerOpp.stage.color}20`,
                      color: drawerOpp.stage.color,
                      border: `1px solid ${drawerOpp.stage.color}40`,
                    } : undefined}
                  >
                    {drawerOpp.stage.name}
                  </span>
                )}
              </div>
            </SheetHeader>

            <div className="flex-1 overflow-y-auto">
              <Tabs defaultValue="resumen" className="h-full flex flex-col">
                <TabsList className="mx-6 mt-4 mb-2 shrink-0 w-auto self-start">
                  <TabsTrigger value="resumen">Resumen</TabsTrigger>
                  <TabsTrigger value="actividad">Actividad</TabsTrigger>
                  <TabsTrigger value="historial">Historial</TabsTrigger>
                  <TabsTrigger value="ia">IA</TabsTrigger>
                </TabsList>

                <div className="flex-1 overflow-y-auto px-6 pb-6">
                  <TabsContent value="resumen" className="mt-4">
                    <ResumenTab opp={drawerOpp} onUpdated={handleUpdated} />
                  </TabsContent>
                  <TabsContent value="actividad" className="mt-4">
                    <ActividadTab activities={drawerOpp.activities} />
                  </TabsContent>
                  <TabsContent value="historial" className="mt-4">
                    <HistorialTab opp={drawerOpp} history={drawerOpp.history} />
                  </TabsContent>
                  <TabsContent value="ia" className="mt-4">
                    <IATab oppId={drawerOpp?.id ?? null} />
                  </TabsContent>
                </div>
              </Tabs>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
