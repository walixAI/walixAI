import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Clock } from "lucide-react";
import { useTasks, type TaskRow } from "@/lib/queries/tasks";
import { CloseTaskDialog } from "@/components/miDia/CloseTaskDialog";
import { WBadge } from "@/components/walix/Badge";
import { ListRowsSkeleton } from "@/components/walix/Skeletons";

function TaskMini({
  task,
  onComplete,
}: {
  task: TaskRow;
  onComplete: (t: TaskRow) => void;
}) {
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-border last:border-0">
      <button
        type="button"
        aria-label="Completar tarea"
        onClick={() => onComplete(task)}
        className="shrink-0 h-4 w-4 rounded-full border-2 border-muted-foreground hover:border-primary transition-colors"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm truncate text-foreground">{task.title ?? task.taskKind ?? "Tarea"}</p>
        {task.leadName && (
          <p className="text-[11px] text-muted-foreground truncate">{task.leadName}</p>
        )}
      </div>
      {task.overdue && <WBadge variant="danger" className="text-[10px] shrink-0">Vencida</WBadge>}
    </div>
  );
}

function TaskSection({
  title,
  icon: Icon,
  tasks,
  loading,
  onComplete,
}: {
  title: string;
  icon: React.ElementType;
  tasks: TaskRow[];
  loading: boolean;
  onComplete: (t: TaskRow) => void;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 mb-2">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</span>
        <span className="ml-auto text-[11px] text-muted-foreground">{tasks.length}</span>
      </div>
      {loading ? (
        <ListRowsSkeleton rows={2} />
      ) : tasks.length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">Sin tareas</p>
      ) : (
        tasks.slice(0, 5).map((t) => (
          <TaskMini key={t.id} task={t} onComplete={onComplete} />
        ))
      )}
    </div>
  );
}

export function TaskCards() {
  const { data: overdue = [], isPending: loadingOverdue } = useTasks({ view: "overdue", mineOnly: true });
  const { data: upcoming = [], isPending: loadingUpcoming } = useTasks({ view: "upcoming", mineOnly: true });
  const [closeTarget, setCloseTarget] = useState<TaskRow | null>(null);

  const hasAny = overdue.length > 0 || upcoming.length > 0;

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold">Mis Tareas</h3>
          <p className="text-xs text-muted-foreground">Vencidas y próximas</p>
        </div>
        <Link
          to="/tasks"
          className="text-xs text-primary hover:underline underline-offset-2"
        >
          Ver todas →
        </Link>
      </div>

      {!hasAny && !loadingOverdue && !loadingUpcoming ? (
        <p className="text-sm text-muted-foreground py-4 text-center">Sin tareas pendientes</p>
      ) : (
        <div className="space-y-4">
          <TaskSection
            title="Vencidas"
            icon={AlertCircle}
            tasks={overdue}
            loading={loadingOverdue}
            onComplete={setCloseTarget}
          />
          <TaskSection
            title="Próximas"
            icon={Clock}
            tasks={upcoming}
            loading={loadingUpcoming}
            onComplete={setCloseTarget}
          />
        </div>
      )}

      {closeTarget && (
        <CloseTaskDialog
          open={!!closeTarget}
          onOpenChange={(o) => !o && setCloseTarget(null)}
          contactId={closeTarget.leadId}
          task={{
            id: closeTarget.id,
            title: closeTarget.title,
            taskKind: closeTarget.taskKind,
            dueDate: closeTarget.dueDate,
          }}
          leadName={closeTarget.leadName}
        />
      )}
    </div>
  );
}
