import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ActivityTimelineItem } from "./ActivityTimelineItem";
import { ActivityFormDialog } from "./ActivityFormDialog";
import { getActivities, createActivity } from "@/lib/queries/activities";
import type { ActivityType, ActivityRow, ActivityCreate } from "@/lib/queries/activities";

const TYPE_FILTERS: { value: ActivityType | "all"; label: string }[] = [
  { value: "all",     label: "Todas" },
  { value: "note",    label: "Notas" },
  { value: "call",    label: "Llamadas" },
  { value: "meeting", label: "Reuniones" },
  { value: "email",   label: "Emails" },
  { value: "task",    label: "Tareas" },
];

interface ContactTabActividadesProps {
  contactId: string;
}

export function ContactTabActividades({ contactId }: ContactTabActividadesProps) {
  const qc = useQueryClient();
  const [typeFilter, setTypeFilter] = useState<ActivityType | "all">("all");
  const [page, setPage] = useState(1);
  const [dialogOpen, setDialogOpen] = useState(false);

  const queryKey = ["activities", contactId, page];

  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: () => getActivities(contactId, { page }),
    staleTime: 30_000,
  });

  const items = data?.items ?? [];
  const filtered = typeFilter === "all" ? items : items.filter((a) => a.activityType === typeFilter);
  const hasMore = data ? page * data.pageSize < data.total : false;

  const createMutation = useMutation({
    mutationFn: (payload: ActivityCreate) => createActivity(contactId, payload),
    onMutate: async (payload) => {
      await qc.cancelQueries({ queryKey: ["activities", contactId] });
      const snapshot = qc.getQueryData<typeof data>(queryKey);
      const optimistic: ActivityRow = {
        id: `optimistic-${Date.now()}`,
        leadId: contactId,
        activityType: payload.activityType,
        title: payload.title ?? null,
        body: payload.body ?? null,
        metadata: payload.metadata ?? null,
        dueDate: payload.dueDate ?? null,
        completedAt: null,
        createdBy: null,
        createdByName: null,
        createdAt: new Date().toISOString(),
      };
      qc.setQueryData(queryKey, (old: typeof data) => {
        if (!old) return old;
        return { ...old, items: [optimistic, ...old.items], total: old.total + 1 };
      });
      return { snapshot };
    },
    onSuccess: () => {
      toast.success("Actividad registrada");
    },
    onError: (e: Error, _vars, ctx) => {
      if (ctx?.snapshot) qc.setQueryData(queryKey, ctx.snapshot);
      toast.error("Error al registrar actividad", { description: e.message });
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["activities", contactId] });
    },
  });

  const handleCreate = async (payload: ActivityCreate) => {
    await createMutation.mutateAsync(payload);
  };

  return (
    <div data-testid="activity-timeline" className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex gap-1.5 flex-wrap">
          {TYPE_FILTERS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              data-testid={`activity-filter-${label}`}
              onClick={() => setTypeFilter(value)}
              className={cn(
                "px-2.5 py-1 rounded-full text-xs font-medium border transition-colors",
                typeFilter === value
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border hover:bg-muted",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <Button data-testid="add-activity-btn" size="sm" className="h-7 gap-1 text-xs shrink-0" onClick={() => setDialogOpen(true)}>
          <Plus className="h-3.5 w-3.5" />
          Registrar
        </Button>
      </div>

      {/* Timeline */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex gap-3 py-2">
              <Skeleton className="h-7 w-7 rounded-full shrink-0" />
              <div className="space-y-1.5 flex-1">
                <Skeleton className="h-3 w-2/3" />
                <Skeleton className="h-3 w-1/3" />
              </div>
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-10">
          <p className="text-sm text-muted-foreground">Sin actividades{typeFilter !== "all" ? " de este tipo" : ""}.</p>
          <Button variant="link" size="sm" className="mt-1" onClick={() => setDialogOpen(true)}>
            + Registrar la primera
          </Button>
        </div>
      ) : (
        <div className="space-y-0.5">
          {filtered.map((activity) => (
            <ActivityTimelineItem
              key={activity.id}
              activity={activity}
              contactId={contactId}
              queryKey={queryKey}
            />
          ))}
        </div>
      )}

      {/* Load more */}
      {hasMore && (
        <div className="text-center pt-1">
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={() => setPage((p) => p + 1)}
            disabled={isLoading}
          >
            Cargar más
          </Button>
        </div>
      )}

      <ActivityFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSubmit={handleCreate}
      />
    </div>
  );
}
