import { useEffect, useState } from "react";
import { Loader2, Sparkles, Users } from "lucide-react";
import { toast } from "sonner";
import {
  useMonthlyGoals,
  useSaveMonthlyGoal,
  useUpdateMonthlyGoal,
  useGoalAssignments,
  type MonthlyGoal,
  type GoalDimension,
} from "@/lib/queries/goals";
import { useProductCategories } from "@/lib/queries/goals";
import { useTenantUsers } from "@/lib/queries/tenantUsers";
import { apiRequest } from "@/lib/queries/_client";
import { useAuth } from "@/hooks/useAuth";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const MONTHS_ES = [
  "Enero","Febrero","Marzo","Abril","Mayo","Junio",
  "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre",
];

const DIMENSION_OPTIONS: { value: GoalDimension; label: string }[] = [
  { value: "global",           label: "Global" },
  { value: "deal_type",        label: "Tipo de venta" },
  { value: "product_category", label: "Categoría de producto" },
  { value: "pipeline",         label: "Etapa de pipeline" },
];

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  periodYear: number;
  periodMonth: number;
  goal?: MonthlyGoal;
}

export function GoalBuilderDialog({ open, onOpenChange, periodYear, periodMonth, goal }: Props) {
  const { tenant } = useAuth();
  const qc = useQueryClient();
  const isEdit = !!goal;

  const dealTypeOptions: string[] = tenant?.deal_type_options ?? ["Venta", "Servicio"];

  // ── Form state ───────────────────────────────────────────────────────────────
  const [dimension, setDimension] = useState<GoalDimension>("global");
  const [dealTypeValue, setDealTypeValue] = useState("");
  const [productCategoryId, setProductCategoryId] = useState("");
  const [pipelineStageId, setPipelineStageId] = useState("");
  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [isDraft, setIsDraft] = useState(false);

  // ── Assignment state ─────────────────────────────────────────────────────────
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([]);
  const [shares, setShares] = useState<Record<string, number>>({});
  const [suggestingHistory, setSuggestingHistory] = useState(false);

  // ── Data queries ─────────────────────────────────────────────────────────────
  const { data: categories = [] } = useProductCategories();
  const { data: users = [] } = useTenantUsers();
  const { data: existingAssignments = [] } = useGoalAssignments(goal?.id);

  // Pipeline stages — fetched only when dimension = pipeline
  const [pipelineStages, setPipelineStages] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => {
    if (dimension !== "pipeline" || !open) return;
    apiRequest<any[]>("/api/pipeline/stages")
      .then((rows) => setPipelineStages((rows ?? []).map((r) => ({ id: r.id, name: r.name }))))
      .catch(() => {});
  }, [dimension, open]);

  // ── Initialize on open ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    if (goal) {
      setDimension(goal.dimension);
      setDealTypeValue(goal.dimensionValueText ?? "");
      setProductCategoryId(goal.dimension === "product_category" ? (goal.dimensionValueUuid ?? "") : "");
      setPipelineStageId(goal.dimension === "pipeline" ? (goal.dimensionValueUuid ?? "") : "");
      setAmount(String(goal.amount));
      setNotes(goal.notes ?? "");
      setIsDraft(goal.isDraft);
    } else {
      setDimension("global");
      setDealTypeValue("");
      setProductCategoryId("");
      setPipelineStageId("");
      setAmount("");
      setNotes("");
      setIsDraft(false);
      setSelectedUserIds([]);
      setShares({});
    }
  }, [open, goal?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Initialize assignments when editing
  useEffect(() => {
    if (!isEdit || !existingAssignments.length) return;
    setSelectedUserIds(existingAssignments.map((a) => a.userId));
    setShares(Object.fromEntries(existingAssignments.map((a) => [a.userId, a.sharePercent])));
  }, [existingAssignments, isEdit]);

  // Reset dimension value when dimension changes
  useEffect(() => {
    setDealTypeValue("");
    setProductCategoryId("");
    setPipelineStageId("");
  }, [dimension]);

  // ── Mutations ────────────────────────────────────────────────────────────────
  const saveGoal = useSaveMonthlyGoal();
  const updateGoal = useUpdateMonthlyGoal();

  // ── Assignment helpers ───────────────────────────────────────────────────────
  function toggleUser(uid: string) {
    setSelectedUserIds((prev) =>
      prev.includes(uid) ? prev.filter((id) => id !== uid) : [...prev, uid],
    );
    setShares((prev) => {
      const next = { ...prev };
      if (selectedUserIds.includes(uid)) delete next[uid];
      return next;
    });
  }

  function distributeEqually() {
    const n = selectedUserIds.length;
    if (n === 0) return;
    const each = Math.round((100 / n) * 100) / 100;
    const newShares: Record<string, number> = {};
    selectedUserIds.forEach((uid, i) => {
      newShares[uid] = i === n - 1 ? Math.round((100 - each * (n - 1)) * 100) / 100 : each;
    });
    setShares(newShares);
  }

  async function handleSuggestByHistory() {
    if (selectedUserIds.length === 0) {
      toast.error("Selecciona al menos un asesor primero");
      return;
    }
    setSuggestingHistory(true);
    try {
      const qs = new URLSearchParams();
      qs.set("dimension", dimension);
      if (dimension === "deal_type" && dealTypeValue) qs.set("dimension_value_text", dealTypeValue);
      if (dimension === "product_category" && productCategoryId) qs.set("dimension_value_uuid", productCategoryId);
      if (dimension === "pipeline" && pipelineStageId) qs.set("dimension_value_uuid", pipelineStageId);
      for (const uid of selectedUserIds) qs.append("user_ids", uid);
      const result = await apiRequest<Record<string, number>>(
        `/api/finance/goal-split-suggestion?${qs.toString()}`,
      );
      if (result && typeof result === "object" && Object.keys(result).length > 0) {
        setShares((prev) => ({
          ...prev,
          ...Object.fromEntries(Object.entries(result).map(([k, v]) => [k, Number(v)])),
        }));
      } else {
        toast.error("Sin datos históricos suficientes para este filtro");
      }
    } catch {
      toast.error("No hay suficientes datos históricos para sugerir un reparto");
    } finally {
      setSuggestingHistory(false);
    }
  }

  // ── Submit ───────────────────────────────────────────────────────────────────
  const activeUsers = users.filter((u) => u.isActive);
  const sumShares = selectedUserIds.reduce((s, uid) => s + (shares[uid] ?? 0), 0);
  const sharesValid = selectedUserIds.length === 0 || Math.abs(sumShares - 100) < 0.01;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const amountNum = parseFloat(amount);
    if (isNaN(amountNum) || amountNum <= 0) {
      toast.error("El monto debe ser mayor a 0");
      return;
    }
    if (!sharesValid) {
      toast.error(`La suma de porcentajes debe ser 100% (actual: ${sumShares.toFixed(1)}%)`);
      return;
    }

    try {
      let goalId: string;

      if (isEdit && goal) {
        await updateGoal.mutateAsync({ id: goal.id, patch: { amount: amountNum, notes: notes || null, isDraft } });
        goalId = goal.id;
      } else {
        const saved = await saveGoal.mutateAsync({
          periodYear,
          periodMonth,
          amount: amountNum,
          dimension,
          dimensionValueText: dimension === "deal_type" ? (dealTypeValue || null) : null,
          dimensionValueUuid:
            dimension === "product_category" ? (productCategoryId || null)
            : dimension === "pipeline" ? (pipelineStageId || null)
            : null,
          notes: notes || null,
          isDraft,
        });
        goalId = (saved as any).id as string;
      }

      if (selectedUserIds.length > 0) {
        await apiRequest(`/api/goals/monthly-goals/${goalId}/assignments`, {
          method: "PUT",
          body: JSON.stringify({
            assignments: selectedUserIds.map((uid) => ({
              user_id: uid,
              share_percent: shares[uid] ?? 0,
            })),
          }),
        });
        qc.invalidateQueries({ queryKey: ["goal-assignments", goalId] });
        qc.invalidateQueries({ queryKey: ["monthly-goals"] });
      }

      toast.success(isEdit ? "Meta actualizada" : "Meta guardada");
      onOpenChange(false);
    } catch (err) {
      toast.error((err as Error).message ?? "Error al guardar");
    }
  }

  const isSaving = saveGoal.isPending || updateGoal.isPending || suggestingHistory;
  const title = isEdit
    ? "Editar meta"
    : `Nueva meta — ${MONTHS_ES[periodMonth - 1]} ${periodYear}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5 mt-1">
          {/* Dimension */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Dimensión</Label>
              <Select
                value={dimension}
                onValueChange={(v) => setDimension(v as GoalDimension)}
                disabled={isEdit}
              >
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DIMENSION_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Dimension value */}
            {dimension === "deal_type" && (
              <div className="space-y-1.5">
                <Label className="text-xs">Tipo de venta</Label>
                <Select value={dealTypeValue} onValueChange={setDealTypeValue} disabled={isEdit}>
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue placeholder="Selecciona…" />
                  </SelectTrigger>
                  <SelectContent>
                    {dealTypeOptions.map((opt) => (
                      <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {dimension === "product_category" && (
              <div className="space-y-1.5">
                <Label className="text-xs">Categoría</Label>
                <Select value={productCategoryId} onValueChange={setProductCategoryId} disabled={isEdit}>
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue placeholder="Selecciona…" />
                  </SelectTrigger>
                  <SelectContent>
                    {categories.map((c) => (
                      <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {dimension === "pipeline" && (
              <div className="space-y-1.5">
                <Label className="text-xs">Etapa</Label>
                <Select value={pipelineStageId} onValueChange={setPipelineStageId} disabled={isEdit}>
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue placeholder="Selecciona…" />
                  </SelectTrigger>
                  <SelectContent>
                    {pipelineStages.map((s) => (
                      <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* Amount */}
          <div className="space-y-1.5">
            <Label className="text-xs">Monto meta (MXN)</Label>
            <Input
              type="number"
              min="1"
              step="any"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="ej. 250000"
              className="h-9 text-sm"
              required
            />
          </div>

          {/* Notes */}
          <div className="space-y-1.5">
            <Label className="text-xs">Notas (opcional)</Label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="text-sm resize-none"
              placeholder="Contexto o aclaraciones…"
            />
          </div>

          {/* Draft toggle */}
          <div className="flex items-center gap-3">
            <Switch id="is-draft" checked={isDraft} onCheckedChange={setIsDraft} />
            <Label htmlFor="is-draft" className="text-sm cursor-pointer">
              Guardar como borrador
            </Label>
          </div>

          {/* Assignment section */}
          <div className="space-y-3 border-t border-border pt-4">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-semibold">Asignación a vendedores</span>
              <span className="text-[11px] text-muted-foreground">(opcional)</span>
            </div>

            <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1">
              {activeUsers.map((u) => {
                const selected = selectedUserIds.includes(u.id);
                return (
                  <div key={u.id} className="flex items-center gap-3">
                    <Checkbox
                      id={`user-${u.id}`}
                      checked={selected}
                      onCheckedChange={() => toggleUser(u.id)}
                    />
                    <Label htmlFor={`user-${u.id}`} className="text-sm flex-1 cursor-pointer">
                      {u.name}
                    </Label>
                    {selected && (
                      <div className="flex items-center gap-1 shrink-0">
                        <Input
                          type="number"
                          min="0"
                          max="100"
                          step="0.1"
                          value={shares[u.id] ?? ""}
                          onChange={(e) =>
                            setShares((prev) => ({ ...prev, [u.id]: parseFloat(e.target.value) || 0 }))
                          }
                          className="h-7 w-20 text-xs text-right"
                        />
                        <span className="text-xs text-muted-foreground">%</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {selectedUserIds.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs gap-1"
                  onClick={distributeEqually}
                >
                  Repartir equitativo
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs gap-1"
                  onClick={handleSuggestByHistory}
                  disabled={suggestingHistory}
                >
                  {suggestingHistory
                    ? <Loader2 className="h-3 w-3 animate-spin" />
                    : <Sparkles className="h-3 w-3" />}
                  Sugerir por historial
                </Button>
                <span
                  className={`text-xs ml-auto ${
                    sharesValid ? "text-muted-foreground" : "text-danger font-semibold"
                  }`}
                >
                  Total: {sumShares.toFixed(1)}%
                </span>
              </div>
            )}
          </div>

          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
              {isEdit ? "Actualizar" : "Guardar meta"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
