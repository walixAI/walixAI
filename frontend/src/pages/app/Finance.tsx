import { useState } from "react";
import { Wallet, Plus, AlertCircle, Lock, Check, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  useExpenses,
  useExpenseCategories,
  useDeleteExpense,
  useConfirmExpense,
  useConfirmAllExpenses,
} from "@/lib/queries/finance";
import type { Expense, ExpenseFilters } from "@/lib/queries/finance";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { WBadge } from "@/components/walix/Badge";
import { ListRowsSkeleton } from "@/components/walix/Skeletons";
import { ExpenseFormDialog } from "@/components/finance/ExpenseFormDialog";
import { ExpenseCategoriesManager } from "@/components/finance/ExpenseCategoriesManager";
import { formatMXN0 } from "@/lib/format/currency";

// ── Helpers ───────────────────────────────────────────────────────────────────

function thisMonth(): string {
  return new Date().toISOString().slice(0, 7); // "YYYY-MM"
}

function monthToApiDate(ym: string): string {
  return `${ym}-01`; // backend accepts any date within the month
}

// ── Expense row ───────────────────────────────────────────────────────────────

function ExpenseRow({
  expense,
  categoryName,
  onConfirm,
  onDelete,
}: {
  expense: Expense;
  categoryName: string;
  onConfirm: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-muted/40 transition-colors border-b border-border last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium truncate">{categoryName}</span>
          <WBadge
            variant={expense.kind === "fijo" ? "neutral" : "brand"}
            className="text-[10px] shrink-0"
          >
            {expense.kind}
          </WBadge>
          {expense.status === "draft" && (
            <WBadge variant="warning" className="text-[10px] shrink-0">
              borrador
            </WBadge>
          )}
        </div>
        {expense.description && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{expense.description}</p>
        )}
        <p className="text-[11px] text-muted-foreground mt-0.5">
          {new Date(`${expense.incurredAt}T12:00:00`).toLocaleDateString("es-MX", {
            day: "numeric",
            month: "short",
            year: "numeric",
          })}
        </p>
      </div>

      <span className="text-sm font-semibold shrink-0">{formatMXN0(expense.amount)}</span>

      <div className="flex items-center gap-1 shrink-0">
        {expense.status === "draft" && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-success hover:text-success"
            title="Confirmar gasto"
            onClick={onConfirm}
          >
            <Check className="h-4 w-4" />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-danger hover:text-danger"
          title="Eliminar gasto"
          onClick={onDelete}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Finance() {
  const [monthFilter, setMonthFilter] = useState(thisMonth());
  const [kindFilter, setKindFilter] = useState<"" | "fijo" | "variable">("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Expense | null>(null);

  const activeFilters: ExpenseFilters = {
    month: monthToApiDate(monthFilter),
    ...(kindFilter ? { kind: kindFilter as "fijo" | "variable" } : {}),
    ...(categoryFilter ? { categoryId: categoryFilter } : {}),
  };

  const { data: expenses = [], isError, error, isPending } = useExpenses(activeFilters);
  const { data: drafts = [] } = useExpenses({ status: "draft" });
  const { data: categories = [] } = useExpenseCategories();

  const confirmExpense = useConfirmExpense();
  const confirmAll = useConfirmAllExpenses();
  const deleteExpense = useDeleteExpense();

  // ── Access denied (403) ───────────────────────────────────────────────────
  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 p-8 text-center">
        <div className="rounded-full bg-muted p-4">
          <Lock className="h-8 w-8 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-foreground">Sin acceso a Finanzas</h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-sm">
            {(error as Error)?.message?.includes("acceso")
              ? "No tienes acceso a Finanzas. Pide a tu administrador que te dé acceso."
              : ((error as Error)?.message ?? "Error al cargar finanzas.")}
          </p>
        </div>
      </div>
    );
  }

  // ── Category lookup map ───────────────────────────────────────────────────
  const categoryMap = Object.fromEntries(categories.map((c) => [c.id, c.name]));

  function catName(exp: Expense): string {
    return exp.categoryId ? (categoryMap[exp.categoryId] ?? "Sin categoría") : "Sin categoría";
  }

  // ── Totals by category (filtered list) ───────────────────────────────────
  const totalByCategory = expenses.reduce<Record<string, number>>((acc, exp) => {
    const key = catName(exp);
    acc[key] = (acc[key] ?? 0) + exp.amount;
    return acc;
  }, {});
  const grandTotal = expenses.reduce((sum, e) => sum + e.amount, 0);

  // ── Confirm all drafts ────────────────────────────────────────────────────
  function handleConfirmAll() {
    confirmAll.mutate(undefined, {
      onSuccess: (res) =>
        toast.success(
          `${res.updated} gasto${res.updated !== 1 ? "s" : ""} confirmado${res.updated !== 1 ? "s" : ""}`,
        ),
      onError: (e) => toast.error((e as Error).message),
    });
  }

  // ── Delete ────────────────────────────────────────────────────────────────
  function handleDeleteConfirm() {
    if (!deleteTarget) return;
    deleteExpense.mutate(deleteTarget.id, {
      onSuccess: () => { toast.success("Gasto eliminado"); setDeleteTarget(null); },
      onError: (e) => toast.error((e as Error).message),
    });
  }

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/10 p-2">
            <Wallet className="h-5 w-5 text-primary" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">Finanzas</h1>
        </div>
        <div className="flex items-center gap-2">
          <ExpenseCategoriesManager />
          <Button size="sm" onClick={() => setFormOpen(true)}>
            <Plus className="h-4 w-4 mr-1" /> Nuevo gasto
          </Button>
        </div>
      </div>

      {/* ProfitabilityCard se agrega en F4 */}

      {/* Draft banner */}
      {drafts.length > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-warning/30 bg-warning/5 px-4 py-3">
          <div className="flex items-center gap-2 min-w-0">
            <AlertCircle className="h-4 w-4 text-warning shrink-0" />
            <p className="text-sm text-warning truncate">
              <span className="font-semibold">{drafts.length}</span>{" "}
              gasto{drafts.length !== 1 ? "s" : ""} pendiente{drafts.length !== 1 ? "s" : ""} de confirmar
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="border-warning/50 text-warning hover:bg-warning/10 shrink-0"
            onClick={handleConfirmAll}
            disabled={confirmAll.isPending}
          >
            {confirmAll.isPending ? "Confirmando…" : "Confirmar todos"}
          </Button>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          type="month"
          value={monthFilter}
          onChange={(e) => setMonthFilter(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
        <Select
          value={kindFilter || "__all__"}
          onValueChange={(v) => setKindFilter(v === "__all__" ? "" : (v as "fijo" | "variable"))}
        >
          <SelectTrigger className="w-32 h-9">
            <SelectValue placeholder="Tipo" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Todos</SelectItem>
            <SelectItem value="fijo">Fijo</SelectItem>
            <SelectItem value="variable">Variable</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={categoryFilter || "__all__"}
          onValueChange={(v) => setCategoryFilter(v === "__all__" ? "" : v)}
        >
          <SelectTrigger className="w-48 h-9">
            <SelectValue placeholder="Categoría" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Todas las categorías</SelectItem>
            {categories
              .filter((c) => c.isActive)
              .map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>

      {/* Totals by category */}
      {expenses.length > 0 && (
        <div className="rounded-xl border border-border bg-card shadow-card p-4">
          <h2 className="text-sm font-semibold text-foreground mb-3">Total por categoría</h2>
          <div className="space-y-2">
            {Object.entries(totalByCategory)
              .sort(([, a], [, b]) => b - a)
              .map(([name, total]) => (
                <div key={name} className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground truncate">{name}</span>
                  <span className="text-sm font-medium shrink-0">{formatMXN0(total)}</span>
                </div>
              ))}
            <div className="flex items-center justify-between gap-4 pt-2 border-t border-border">
              <span className="text-sm font-semibold">Total</span>
              <span className="text-sm font-bold">{formatMXN0(grandTotal)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Expense list */}
      <div className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
        {isPending ? (
          <div className="p-4">
            <ListRowsSkeleton rows={5} showAvatar={false} />
          </div>
        ) : expenses.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-muted-foreground">
            Sin gastos en este periodo.
          </p>
        ) : (
          expenses.map((exp) => (
            <ExpenseRow
              key={exp.id}
              expense={exp}
              categoryName={catName(exp)}
              onConfirm={() =>
                confirmExpense.mutate(
                  { id: exp.id },
                  {
                    onSuccess: () => toast.success("Gasto confirmado"),
                    onError: (e) => toast.error((e as Error).message),
                  },
                )
              }
              onDelete={() => setDeleteTarget(exp)}
            />
          ))
        )}
      </div>

      {/* Expense form */}
      <ExpenseFormDialog open={formOpen} onOpenChange={setFormOpen} />

      {/* Delete confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar gasto?</AlertDialogTitle>
            <AlertDialogDescription>
              Se eliminará permanentemente
              {deleteTarget?.description ? ` "${deleteTarget.description}"` : " este gasto"}.
              Esta acción no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-danger text-white hover:bg-danger/90"
            >
              {deleteExpense.isPending ? "Eliminando…" : "Eliminar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
