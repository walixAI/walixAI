import { useState } from "react";
import { ChevronLeft, ChevronRight, Loader2, Pencil, Plus } from "lucide-react";
import { toast } from "sonner";
import { useMonthlyGoals, useUpdateMonthlyGoal, useProductCategories } from "@/lib/queries/goals";
import type { MonthlyGoal } from "@/lib/queries/goals";
import { GoalBuilderDialog } from "./GoalBuilderDialog";
import { Button } from "@/components/ui/button";
import { WBadge } from "@/components/walix/Badge";
import { formatMXN0 } from "@/lib/format/currency";

const MONTHS_ES = [
  "Enero","Febrero","Marzo","Abril","Mayo","Junio",
  "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre",
];

function prevMonth(year: number, month: number): [number, number] {
  return month === 1 ? [year - 1, 12] : [year, month - 1];
}
function nextMonth(year: number, month: number): [number, number] {
  return month === 12 ? [year + 1, 1] : [year, month + 1];
}

function dimensionLabel(goal: MonthlyGoal, categoryMap: Record<string, string>): string {
  switch (goal.dimension) {
    case "global":           return "Global";
    case "deal_type":        return `Tipo: ${goal.dimensionValueText ?? "—"}`;
    case "product_category": return `Producto: ${categoryMap[goal.dimensionValueUuid ?? ""] ?? "—"}`;
    case "pipeline":         return `Pipeline: ${goal.dimensionValueUuid?.slice(0, 8) ?? "—"}`;
  }
}

// ── Goal row ──────────────────────────────────────────────────────────────────

function GoalRow({
  goal,
  categoryMap,
  onEdit,
}: {
  goal: MonthlyGoal;
  categoryMap: Record<string, string>;
  onEdit: () => void;
}) {
  const updateGoal = useUpdateMonthlyGoal();

  function markAsDraft() {
    updateGoal.mutate(
      { id: goal.id, patch: { isDraft: true } },
      {
        onSuccess: () => toast.success("Meta marcada como borrador"),
        onError: (e) => toast.error((e as Error).message),
      },
    );
  }

  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors border-b border-border last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium">{dimensionLabel(goal, categoryMap)}</span>
          {goal.isDraft && (
            <WBadge variant="warning" className="text-[10px]">borrador</WBadge>
          )}
        </div>
        {goal.notes && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{goal.notes}</p>
        )}
      </div>

      <span className="text-sm font-semibold shrink-0">{formatMXN0(goal.amount)}</span>

      <div className="flex items-center gap-1 shrink-0">
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onEdit} title="Editar">
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        {!goal.isDraft && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-[11px] text-muted-foreground hover:text-foreground px-2"
            onClick={markAsDraft}
            disabled={updateGoal.isPending}
            title="Marcar como borrador"
          >
            Borrador
          </Button>
        )}
      </div>
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────────────────────────

export function GoalsListCard() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<MonthlyGoal | undefined>(undefined);

  const { data: goals = [], isPending } = useMonthlyGoals({
    periodYear: year,
    periodMonth: month,
    includeDraft: true,
  });
  const { data: categories = [] } = useProductCategories(true);

  const categoryMap: Record<string, string> = Object.fromEntries(
    categories.map((c) => [c.id, c.name]),
  );

  function handlePrev() {
    const [ny, nm] = prevMonth(year, month);
    setYear(ny);
    setMonth(nm);
  }
  function handleNext() {
    const [ny, nm] = nextMonth(year, month);
    setYear(ny);
    setMonth(nm);
  }

  function openCreate() {
    setEditingGoal(undefined);
    setDialogOpen(true);
  }
  function openEdit(goal: MonthlyGoal) {
    setEditingGoal(goal);
    setDialogOpen(true);
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold">Metas mensuales</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Define cuánto debe vender el equipo este mes.
          </p>
        </div>
        <Button size="sm" className="gap-1.5" onClick={openCreate}>
          <Plus className="h-3.5 w-3.5" />
          Nueva meta
        </Button>
      </div>

      {/* Period selector */}
      <div className="flex items-center gap-2">
        <button
          onClick={handlePrev}
          className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-sm font-semibold min-w-[130px] text-center">
          {MONTHS_ES[month - 1]} {year}
        </span>
        <button
          onClick={handleNext}
          className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Goals list */}
      <div className="rounded-lg border border-border overflow-hidden">
        {isPending ? (
          <div className="flex items-center gap-2 px-4 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Cargando metas…
          </div>
        ) : goals.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-muted-foreground">
            Sin metas para {MONTHS_ES[month - 1]} {year}.
          </p>
        ) : (
          goals.map((goal) => (
            <GoalRow
              key={goal.id}
              goal={goal}
              categoryMap={categoryMap}
              onEdit={() => openEdit(goal)}
            />
          ))
        )}
      </div>

      <GoalBuilderDialog
        open={dialogOpen}
        onOpenChange={(o) => { setDialogOpen(o); if (!o) setEditingGoal(undefined); }}
        periodYear={year}
        periodMonth={month}
        goal={editingGoal}
      />
    </div>
  );
}
