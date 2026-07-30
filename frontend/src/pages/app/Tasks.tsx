import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ListTodo, Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useTasks, useDeleteTask, type TaskRow, type TaskView } from "@/lib/queries/tasks";
import { updateActivity } from "@/lib/queries/activities";
import { CloseTaskDialog } from "@/components/miDia/CloseTaskDialog";
import { QuickTaskDialog } from "@/components/miDia/QuickTaskDialog";
import { WBadge } from "@/components/walix/Badge";
import { Button } from "@/components/ui/button";
import { ListRowsSkeleton } from "@/components/walix/Skeletons";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

// ── Tab config ────────────────────────────────────────────────────────────────

const TABS: { key: string; label: string; view: TaskView }[] = [
  { key: "hoy",         label: "Hoy",         view: "today" },
  { key: "proximas",    label: "Próximas",     view: "upcoming" },
  { key: "vencidas",    label: "Vencidas",     view: "overdue" },
  { key: "completadas", label: "Completadas",  view: "completed" },
  { key: "todas",       label: "Todas",        view: "all" },
];

// ── Row component ─────────────────────────────────────────────────────────────

function TaskRow({
  task,
  onCheck,
  onUncheck,
  onEdit,
  onDelete,
}: {
  task: TaskRow;
  onCheck: (t: TaskRow) => void;
  onUncheck: (t: TaskRow) => void;
  onEdit: (t: TaskRow) => void;
  onDelete: (t: TaskRow) => void;
}) {
  const done = !!task.completedAt;
  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-muted/40 transition-colors border-b border-border last:border-0">
      <button
        type="button"
        aria-label={done ? "Marcar como pendiente" : "Completar tarea"}
        onClick={() => (done ? onUncheck(task) : onCheck(task))}
        className="shrink-0 text-muted-foreground hover:text-primary transition-colors"
      >
        {done ? (
          <div className="h-5 w-5 rounded-full border-2 border-primary bg-primary/10 flex items-center justify-center">
            <div className="h-2 w-2 rounded-full bg-primary" />
          </div>
        ) : (
          <div className="h-5 w-5 rounded-full border-2 border-muted-foreground" />
        )}
      </button>

      <div className="flex-1 min-w-0">
        <p className={cn("text-sm font-medium truncate", done && "line-through text-muted-foreground")}>
          {task.title ?? task.taskKind ?? "Tarea"}
        </p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {task.leadName && (
            <span className="text-xs text-muted-foreground truncate">{task.leadName}</span>
          )}
          {task.taskKind && (
            <WBadge variant="neutral" className="text-[10px]">{task.taskKind}</WBadge>
          )}
          {task.overdue && !done && (
            <WBadge variant="danger" className="text-[10px]">Vencida</WBadge>
          )}
          {task.dueDate && (
            <span className="text-[10px] text-muted-foreground">
              {new Date(task.dueDate).toLocaleDateString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 shrink-0">
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onEdit(task)}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7 text-danger hover:text-danger" onClick={() => onDelete(task)}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Tasks() {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = searchParams.get("view") ?? "hoy";
  const [mineOnly, setMineOnly] = useState(true);

  const [closeDialog, setCloseDialog] = useState<TaskRow | null>(null);
  const [editTask, setEditTask] = useState<TaskRow | null>(null);
  const [quickOpen, setQuickOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TaskRow | null>(null);

  const activeTab = TABS.find((t) => t.key === currentTab) ?? TABS[0];
  const { data: tasks = [], isPending } = useTasks({ view: activeTab.view, mineOnly });
  const deleteTask = useDeleteTask();

  const qc = useQueryClient();
  const unmarkMutation = useMutation({
    mutationFn: (task: TaskRow) =>
      updateActivity(task.leadId, task.id, { completedAt: null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["tasks-today"] });
      toast.success("Tarea marcada como pendiente");
    },
    onError: (e) => toast.error((e as Error).message ?? "Error"),
  });

  function handleCheck(task: TaskRow) {
    setCloseDialog(task);
  }

  function handleUncheck(task: TaskRow) {
    unmarkMutation.mutate(task);
  }

  function handleDeleteConfirm() {
    if (!deleteTarget) return;
    deleteTask.mutate(deleteTarget.id, {
      onSuccess: () => { toast.success("Tarea eliminada"); setDeleteTarget(null); },
      onError: (e) => toast.error((e as Error).message ?? "Error al eliminar"),
    });
  }

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/10 p-2">
            <ListTodo className="h-5 w-5 text-primary" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">Tareas</h1>
        </div>
        <Button size="sm" onClick={() => { setEditTask(null); setQuickOpen(true); }}>
          <Plus className="h-4 w-4 mr-1" /> Nueva tarea
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex gap-1 rounded-lg bg-muted p-1">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setSearchParams({ view: tab.key })}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                currentTab === tab.key
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <Switch
            id="mine-only"
            checked={mineOnly}
            onCheckedChange={setMineOnly}
          />
          <Label htmlFor="mine-only" className="text-sm cursor-pointer">
            {mineOnly ? "Solo mías" : "De todos"}
          </Label>
        </div>
      </div>

      {/* Task list */}
      <div className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
        {isPending ? (
          <div className="p-4"><ListRowsSkeleton rows={5} /></div>
        ) : tasks.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-muted-foreground">
            Sin tareas en esta vista.
          </p>
        ) : (
          tasks.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              onCheck={handleCheck}
              onUncheck={handleUncheck}
              onEdit={(t) => { setEditTask(t); setQuickOpen(true); }}
              onDelete={setDeleteTarget}
            />
          ))
        )}
      </div>

      {/* CloseTaskDialog — completes with evidence */}
      {closeDialog && (
        <CloseTaskDialog
          open={!!closeDialog}
          onOpenChange={(o) => !o && setCloseDialog(null)}
          contactId={closeDialog.leadId}
          task={{
            id: closeDialog.id,
            title: closeDialog.title,
            taskKind: closeDialog.taskKind,
            dueDate: closeDialog.dueDate,
          }}
          leadName={closeDialog.leadName}
        />
      )}

      {/* QuickTaskDialog — create / edit */}
      <QuickTaskDialog
        open={quickOpen}
        onOpenChange={(o) => { setQuickOpen(o); if (!o) setEditTask(null); }}
        task={editTask ?? undefined}
      />

      {/* Delete AlertDialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar tarea?</AlertDialogTitle>
            <AlertDialogDescription>
              Se eliminará permanentemente "{deleteTarget?.title ?? "esta tarea"}". Esta acción no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-danger text-white hover:bg-danger/90"
            >
              {deleteTask.isPending ? "Eliminando…" : "Eliminar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
