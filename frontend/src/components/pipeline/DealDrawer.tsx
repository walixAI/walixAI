import { useEffect, useState } from "react";
import { ArrowRight, Pencil, Save, X } from "lucide-react";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import { toast } from "sonner";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { WBadge } from "@/components/walix/Badge";
import {
  formatMXN, useUpdateDeal, useStageHistory,
  type PipelineDeal, type PipelineStage,
} from "@/lib/queries/pipeline";
import { useTenantUsers } from "@/lib/queries/tenantUsers";
import { relativeTime } from "@/lib/format/relativeTime";
import { cn } from "@/lib/utils";

const sources = ["WhatsApp", "Formulario web", "Referido", "Manual"];
const UNASSIGNED = "__unassigned__";

interface Props {
  deal: PipelineDeal | null;
  stages: PipelineStage[];
  open: boolean;
  onClose: () => void;
  contactName?: string;
}

export function DealDrawer({ deal, stages, open, onClose, contactName }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<any>({});
  const update = useUpdateDeal();
  const { data: users = [] } = useTenantUsers();

  useEffect(() => {
    if (deal) {
      setDraft({
        name: deal.name,
        amount: deal.amount,
        probability: deal.probability,
        stage_id: deal.stageId,
        owner_id: deal.ownerId ?? UNASSIGNED,
        expected_close_date: deal.expectedCloseDate ?? "",
        source: deal.source,
        notes: deal.notes ?? "",
      });
      setEditing(false);
    }
  }, [deal]);

  const { data: stageHistory = [] } = useStageHistory(deal?.id);

  const lastStageChangeAt = stageHistory[0]?.changedAt ?? deal?.updatedAt ?? null;
  const daysInStage = lastStageChangeAt
    ? Math.max(0, Math.floor((Date.now() - new Date(lastStageChangeAt).getTime()) / 86_400_000))
    : 0;

  if (!deal) return null;

  async function save() {
    if (!deal) return;
    const stage = stages.find((s) => s.id === draft.stage_id);
    const stageChanged = draft.stage_id !== deal.stageId;
    try {
      await update.mutateAsync({
        dealId: deal.id,
        patch: {
          title: draft.name,                                  // name→title
          amount: Number(draft.amount),
          probability: Number(draft.probability),             // explícito → respeta el valor editado
          pipeline_stage_id: draft.stage_id,                  // sin stage_name (lo resuelve el backend)
          ...(stageChanged && stage
            ? { is_won: stage.isWon, is_lost: stage.isLost }
            : {}),
          owner_id: draft.owner_id === UNASSIGNED ? null : draft.owner_id,
          expected_close_date: draft.expected_close_date || null,
          source: draft.source,
          notes: draft.notes || null,
        },
      });
      toast.success("Oportunidad actualizada");
      setEditing(false);
    } catch (e: any) {
      toast.error(e?.message ?? "Error al guardar");
    }
  }

  const ownerLabel = deal.ownerName;

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-[480px] p-0 flex flex-col">
        <SheetHeader className="px-5 py-4 border-b border-border">
          <div className="flex items-center justify-between gap-2">
            <SheetTitle className="truncate">{deal.name}</SheetTitle>
            <div className="flex items-center gap-1">
              {!editing ? (
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setEditing(true)}>
                  <Pencil className="h-4 w-4" />
                </Button>
              ) : (
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={save} disabled={update.isPending}>
                  <Save className="h-4 w-4 text-success" />
                </Button>
              )}
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="flex items-center gap-2 pt-1">
            <span className="text-success font-bold text-lg">{formatMXN(deal.amount)} MXN</span>
            <WBadge variant={deal.isWon ? "success" : deal.isLost ? "danger" : "info"}>{deal.stageName}</WBadge>
          </div>
          {contactName && (
            <div className="text-xs text-muted-foreground">Contacto: {contactName}</div>
          )}
        </SheetHeader>

        <Tabs defaultValue="summary" className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="mx-5 mt-3 grid grid-cols-2">
            <TabsTrigger value="summary">Resumen</TabsTrigger>
            <TabsTrigger value="history">Historial</TabsTrigger>
            {/* FASE 2: pestañas "Actividad" e "IA" */}
          </TabsList>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            <TabsContent value="summary" className="space-y-4 m-0">
              <Field label="Monto MXN">
                {editing ? (
                  <Input type="number" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} />
                ) : <ReadValue>{formatMXN(deal.amount)}</ReadValue>}
              </Field>

              <Field label="Etapa">
                {editing ? (
                  <Select value={draft.stage_id} onValueChange={(v) => setDraft({ ...draft, stage_id: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {stages.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                ) : <ReadValue>{deal.stageName}</ReadValue>}
              </Field>

              <Field label="Dueño">
                {editing ? (
                  <Select value={draft.owner_id} onValueChange={(v) => setDraft({ ...draft, owner_id: v })}>
                    <SelectTrigger><SelectValue placeholder="Sin asignar" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={UNASSIGNED}>Sin asignar</SelectItem>
                      {users.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                ) : <ReadValue>{ownerLabel}</ReadValue>}
              </Field>

              <Field label="Fecha estimada de cierre">
                {editing ? (
                  <Input type="date" value={draft.expected_close_date ?? ""} onChange={(e) => setDraft({ ...draft, expected_close_date: e.target.value })} />
                ) : <ReadValue>{deal.expectedCloseDate ? format(new Date(deal.expectedCloseDate), "PPP", { locale: es }) : "—"}</ReadValue>}
              </Field>

              <Field label={`Probabilidad: ${editing ? draft.probability : deal.probability}%`}>
                {editing ? (
                  <Slider value={[Number(draft.probability)]} onValueChange={([v]) => setDraft({ ...draft, probability: v })} min={0} max={100} step={5} />
                ) : (
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={cn("h-full", deal.probability >= 70 ? "bg-success" : deal.probability >= 40 ? "bg-warning" : "bg-danger")}
                      style={{ width: `${deal.probability}%` }}
                    />
                  </div>
                )}
              </Field>

              <Field label="Fuente">
                {editing ? (
                  <Select value={draft.source} onValueChange={(v) => setDraft({ ...draft, source: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {sources.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                ) : <ReadValue>{deal.source}</ReadValue>}
              </Field>

              <Field label="Notas">
                {editing ? (
                  <Textarea rows={3} value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
                ) : <ReadValue>{deal.notes ?? "—"}</ReadValue>}
              </Field>
            </TabsContent>

            <TabsContent value="history" className="space-y-3 m-0">
              <div className="rounded-xl border border-border bg-card p-4">
                <div className="text-xs uppercase tracking-wide text-muted-foreground font-semibold mb-1">
                  Tiempo en etapa actual
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold">{daysInStage}</span>
                  <span className="text-sm text-muted-foreground">{daysInStage === 1 ? "día" : "días"} en "{deal.stageName}"</span>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-xs uppercase tracking-wide text-muted-foreground font-semibold">
                  Cambios de etapa
                </div>
                {stageHistory.length === 0 && (
                  <div className="text-sm text-muted-foreground italic py-4 text-center">
                    Sin historial de cambios.
                  </div>
                )}
                {stageHistory.map((h) => (
                  <div key={h.id} className="flex items-center gap-2 text-sm rounded-md border border-border bg-card px-3 py-2">
                    <span className="text-muted-foreground">{h.fromStageName ?? "Inicio"}</span>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span className="font-medium flex-1 truncate">{h.toStageName ?? "—"}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{relativeTime(h.changedAt)}</span>
                  </div>
                ))}
              </div>
            </TabsContent>
          </div>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

function ReadValue({ children }: { children: React.ReactNode }) {
  return <div className="text-sm font-medium px-3 py-2 rounded-md bg-muted/40">{children}</div>;
}

/* FASE 2 (removido): pestañas Actividad e IA, AiContextPanel/Memoria IA,
   useDealActivity, useDealAiSuggestions, useScoreProbability, useSuggestNextStep,
   bloque "Generar propuesta PDF (Pro)". */
