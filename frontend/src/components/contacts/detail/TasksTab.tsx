import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useTasks, useDeleteTask, type TaskRow } from "@/lib/queries/tasks";
import { updateActivity } from "@/lib/queries/activities";
import { CloseTaskDialog } from "@/components/miDia/CloseTaskDialog";
import { QuickTaskDialog } from "@/components/miDia/QuickTaskDialog";
import { WBadge } from "@/components/walix/Badge";
import { Button } from "@/components/ui/button";
import { ListRowsSkeleton } from "@/components/walix/Skeletons";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

interface Props {
  contactId: string;
  contactName?: string | null;
}

export function TasksTab({ contactId, contactName }: Props) {
  const qc = useQueryClient();
  const { data: tasks = [], isPending } = useTasks({ view: "all", mineOnly: false, contactId });
  const deleteTask = useDeleteTask();

  const [closeDialog, setCloseDialog] = useState<TaskRow | null>(null);
  const [editTask, setEditTask] = useState<TaskRow | null>(null);
  const [quickOpen, setQuickOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TaskRow | null>(null);

  const unmarkMutation = useMutation({
    mutationFn: (task: TaskRow) =>
      updateActivity(task.leadId, task.id, { completedAt: null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["tasks-today"] });
      qc.invalidateQueries({ queryKey: ["activities", contactId] });
      toast.success("Tarea marcada como pendiente");
    },
    onError: (e) => toast.error((e as Error).message ?? "Error"),
  });

  function handleDeleteConfirm() {
    if (!deleteTarget) return;
    deleteTask.mutate(deleteTarget.id, {
      onSuccess: () => { toast.success("Tarea eliminada"); setDeleteTarget(null); },
      onError: (e) => toast.error((e as Error).message ?? "Error al eliminar"),
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">
          {tasks.length} {tasks.length === 1 ? "tarea" : "tareas"}
        </span>
        <Button
          size="sm"
          variant="outline"
          onClick={() => { setEditTask(null); setQuickOpen(true); }}
        >
          <Plus className="h-3.5 w-3.5 mr-1" /> Nueva tarea
        </Button>
      </div>

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        {isPending ? (
          <div className="p-4"><ListRowsSkeleton rows={3} /></div>
        ) : tasks.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">
            Sin tareas para este contacto.
          </p>
        ) : (
          tasks.map((task) => {
            const done = !!task.completedAt;
            return (
              <div
                key={task.id}
                className="flex items-center gap-3 px-4 py-3 hover:bg-muted/40 transition-colors border-b border-border last:border-0"
              >
                <button
                  type="button"
                  aria-label={done ? "Marcar como pendiente" : "Completar tarea"}
                  onClick={() => done ? unmarkMutation.mutate(task) : setCloseDialog(task)}
                  className="shrink-0 text-muted-foreground hover:text-primary transition-colors"
                >
                  <div className={cn(
                    "h-5 w-5 rounded-full border-2 flex items-center justify-center",
                    done ? "border-primary bg-primary/10" : "border-muted-foreground",
                  )}>
                    {done && <div className="h-2 w-2 rounded-full bg-primary" />}
                  </div>
                </button>

                <div className="flex-1 min-w-0">
                  <p className={cn("text-sm font-medium truncate", done && "line-through text-muted-foreground")}>
                    {task.title ?? task.taskKind ?? "Tarea"}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5 flex-wrap">
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
                    {task.assigneeName && (
                      <span className="text-[10px] text-muted-foreground">→ {task.assigneeName}</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <Button
                    variant="ghost" size="icon" className="h-7 w-7"
                    onClick={() => { setEditTask(task); setQuickOpen(true); }}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost" size="icon" className="h-7 w-7 text-danger hover:text-danger"
                    onClick={() => setDeleteTarget(task)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            );
          })
        )}
      </div>

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
          leadName={closeDialog.leadName ?? contactName}
        />
      )}

      <QuickTaskDialog
        open={quickOpen}
        onOpenChange={(o) => { setQuickOpen(o); if (!o) setEditTask(null); }}
        contactId={contactId}
        contactName={contactName ?? undefined}
        task={editTask ?? undefined}
      />

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
