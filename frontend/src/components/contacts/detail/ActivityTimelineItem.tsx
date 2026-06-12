import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  MessageSquare,
  CheckSquare,
  Phone,
  Calendar,
  Mail,
  Bot,
  Square,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { updateActivity } from "@/lib/queries/activities";
import type { ActivityRow, ActivityType } from "@/lib/queries/activities";

const ICONS: Record<ActivityType, React.ElementType> = {
  note:    MessageSquare,
  task:    CheckSquare,
  call:    Phone,
  meeting: Calendar,
  email:   Mail,
  system:  Bot,
};

const ICON_COLOR: Record<ActivityType, string> = {
  note:    "text-blue-500 bg-blue-50 dark:bg-blue-900/20",
  task:    "text-amber-500 bg-amber-50 dark:bg-amber-900/20",
  call:    "text-green-500 bg-green-50 dark:bg-green-900/20",
  meeting: "text-purple-500 bg-purple-50 dark:bg-purple-900/20",
  email:   "text-sky-500 bg-sky-50 dark:bg-sky-900/20",
  system:  "text-gray-400 bg-gray-50 dark:bg-gray-800",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("es-MX", { day: "2-digit", month: "short", year: "numeric" });
}

function isOverdue(dueDate: string | null, completedAt: string | null): boolean {
  if (!dueDate || completedAt) return false;
  return new Date(dueDate) < new Date();
}

interface ActivityTimelineItemProps {
  activity: ActivityRow;
  contactId: string;
  queryKey: unknown[];
}

export function ActivityTimelineItem({ activity, contactId, queryKey }: ActivityTimelineItemProps) {
  const qc = useQueryClient();
  const isSystem = activity.activityType === "system";
  const isTask = activity.activityType === "task";
  const overdue = isOverdue(activity.dueDate, activity.completedAt);
  const completed = Boolean(activity.completedAt);

  const Icon = ICONS[activity.activityType] ?? MessageSquare;
  const iconColorClass = ICON_COLOR[activity.activityType] ?? ICON_COLOR.note;

  const completeMutation = useMutation({
    mutationFn: () =>
      updateActivity(contactId, activity.id, {
        completedAt: new Date().toISOString(),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
      toast.success("Tarea completada");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div
      data-testid="activity-item"
      className={cn(
        "flex gap-3 py-2.5 px-3 rounded-lg transition-colors",
        isSystem && "bg-muted/40",
        completed && "opacity-60",
      )}
    >
      {/* Icon */}
      <div
        data-testid="activity-type-icon"
        data-type={activity.activityType}
        className={cn("h-7 w-7 rounded-full flex items-center justify-center shrink-0 mt-0.5", iconColorClass)}
      >
        <Icon className="h-3.5 w-3.5" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 space-y-0.5">
        {activity.title && (
          <p className={cn("text-sm font-medium leading-snug", isSystem && "italic text-muted-foreground")}>
            {activity.title}
          </p>
        )}
        {activity.body && (
          <p className={cn("text-xs text-muted-foreground leading-relaxed", isSystem && "italic")}>
            {activity.body}
          </p>
        )}

        <div className="flex items-center gap-2 flex-wrap mt-1">
          <span className="text-[10px] text-muted-foreground">
            {formatDate(activity.createdAt)}
          </span>
          {activity.createdByName && (
            <span className="text-[10px] text-muted-foreground">· {activity.createdByName}</span>
          )}
          {activity.dueDate && (
            <span className={cn(
              "text-[10px] font-medium px-1.5 py-0.5 rounded-full",
              overdue
                ? "bg-destructive/10 text-destructive border border-destructive/20"
                : "bg-muted text-muted-foreground",
            )}>
              {overdue ? "⚠ Vencida" : `Vence ${formatDate(activity.dueDate)}`}
            </span>
          )}
        </div>
      </div>

      {/* Task completion toggle */}
      {isTask && !isSystem && (
        <button
          type="button"
          className="shrink-0 mt-0.5 hover:opacity-70 transition-opacity"
          onClick={() => !completed && completeMutation.mutate()}
          disabled={completed || completeMutation.isPending}
          aria-label={completed ? "Tarea completada" : "Marcar completada"}
        >
          {completed ? (
            <CheckSquare className="h-4 w-4 text-success" />
          ) : (
            <Square className="h-4 w-4 text-muted-foreground" />
          )}
        </button>
      )}
    </div>
  );
}
