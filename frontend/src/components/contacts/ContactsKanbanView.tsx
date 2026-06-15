import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  useDraggable,
  pointerWithin,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { ContactStatusBadge, STATUS_CONFIG } from "@/components/ui/ContactStatusBadge";
import { ContactAvatar } from "@/components/ui/ContactAvatar";
import { LeadScoreBadge } from "@/components/leads/LeadScoreBadge";
import { updateContact } from "@/lib/queries/contacts";
import type { ContactRow, ContactListResponse, LeadStatus, ContactFilters } from "@/lib/queries/contacts";
import { useTenantLabels } from "@/hooks/useTenantLabels";

const KANBAN_COLUMNS: LeadStatus[] = [
  "nuevo", "en_calificacion", "calificado", "escalado", "perdido",
];

// ── Card content (pure) ───────────────────────────────────────────────────────

function ContactCardContent({ contact }: { contact: ContactRow }) {
  const fullName = [contact.name, contact.lastName].filter(Boolean).join(" ") || "Sin nombre";
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2.5 space-y-2 w-full pointer-events-none">
      <div className="flex items-center gap-2">
        <ContactAvatar id={contact.id} name={contact.name} lastName={contact.lastName} size="sm" />
        <p className="text-sm font-medium truncate flex-1">{fullName}</p>
        {contact.currentScore != null && (
          <LeadScoreBadge
            score={contact.currentScore}
            trend={contact.currentScoreTrend as "up" | "down" | "flat" | null}
          />
        )}
      </div>
      {contact.company && (
        <p className="text-xs text-muted-foreground truncate">{contact.company}</p>
      )}
    </div>
  );
}

// ── Draggable card ────────────────────────────────────────────────────────────

function DraggableCard({
  contact,
  onClick,
}: {
  contact: ContactRow;
  onClick: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: contact.id,
    data: { contact },
  });
  const style = transform ? { transform: CSS.Translate.toString(transform) } : undefined;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={cn(
        "cursor-pointer touch-none select-none transition-opacity",
        isDragging && "opacity-30",
      )}
    >
      <ContactCardContent contact={contact} />
    </div>
  );
}

// ── Droppable column ──────────────────────────────────────────────────────────

function KanbanColumn({
  status,
  contacts,
  onCardClick,
}: {
  status: LeadStatus;
  contacts: ContactRow[];
  onCardClick: (contact: ContactRow) => void;
}) {
  const { isOver, setNodeRef } = useDroppable({ id: status });
  const cfg = STATUS_CONFIG[status];
  const { entity } = useTenantLabels();

  return (
    <div data-testid={`kanban-column-${status}`} className="w-[240px] shrink-0 flex flex-col rounded-xl border border-border bg-card/50">
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <span className="text-sm font-semibold truncate flex-1">{cfg.label}</span>
        <span
          className={cn(
            "text-xs font-medium tabular-nums px-1.5 py-0.5 rounded-full shrink-0",
            contacts.length > 0 ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
          )}
        >
          {contacts.length}
        </span>
      </div>
      <div
        ref={setNodeRef}
        className={cn(
          "flex-1 overflow-y-auto p-2 space-y-2 min-h-[120px] rounded-b-xl transition-colors duration-150",
          isOver && "bg-primary/5",
        )}
      >
        {contacts.length === 0 ? (
          <p className="text-[11px] text-muted-foreground text-center py-8 select-none">
            Sin {entity.toLowerCase()}s
          </p>
        ) : (
          contacts.map((c) => (
            <DraggableCard key={c.id} contact={c} onClick={() => onCardClick(c)} />
          ))
        )}
      </div>
    </div>
  );
}

// ── Board ─────────────────────────────────────────────────────────────────────

interface ContactsKanbanViewProps {
  data: ContactListResponse | undefined;
  isLoading: boolean;
  filters: ContactFilters;
  queryKey: unknown[];
  onCardClick: (contact: ContactRow) => void;
}

export function ContactsKanbanView({
  data,
  isLoading,
  queryKey,
  onCardClick,
}: ContactsKanbanViewProps) {
  const qc = useQueryClient();
  const [activeContact, setActiveContact] = useState<ContactRow | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const grouped = KANBAN_COLUMNS.reduce(
    (acc, s) => {
      acc[s] = (data?.items ?? []).filter((c) => c.status === s);
      return acc;
    },
    {} as Record<LeadStatus, ContactRow[]>,
  );

  const handleDragStart = useCallback(({ active }: DragStartEvent) => {
    setActiveContact((active.data.current?.contact as ContactRow) ?? null);
  }, []);

  const handleDragEnd = useCallback(
    ({ active, over }: DragEndEvent) => {
      setActiveContact(null);
      if (!over) return;

      const contactId = active.id as string;
      const newStatus = over.id as LeadStatus;
      const contact = data?.items.find((c) => c.id === contactId);
      if (!contact || contact.status === newStatus) return;

      const snapshot = qc.getQueryData<ContactListResponse>(queryKey);

      qc.setQueryData<ContactListResponse>(queryKey, (old) => {
        if (!old) return old;
        return {
          ...old,
          items: old.items.map((c) =>
            c.id === contactId ? { ...c, status: newStatus } : c,
          ),
        };
      });

      updateContact(contactId, { status: newStatus })
        .then(() => toast.success("Estado actualizado"))
        .catch((e: Error) => {
          if (snapshot) qc.setQueryData(queryKey, snapshot);
          toast.error("Error al actualizar estado", { description: e.message });
        });
    },
    [data, queryKey, qc],
  );

  if (isLoading) {
    return (
      <div className="flex gap-3 overflow-x-auto pb-2">
        {KANBAN_COLUMNS.map((s) => (
          <div key={s} className="w-[240px] shrink-0 rounded-xl border border-border bg-card/50 p-3 space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {data && data.total > data.items.length && (
        <p className="text-xs text-muted-foreground px-1">
          Mostrando {data.items.length} de {data.total} contactos. Usa filtros por estado para ver más.
        </p>
      )}
      <DndContext
        sensors={sensors}
        collisionDetection={pointerWithin}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="flex gap-3 overflow-x-auto pb-2">
          {KANBAN_COLUMNS.map((status) => (
            <KanbanColumn
              key={status}
              status={status}
              contacts={grouped[status]}
              onCardClick={onCardClick}
            />
          ))}
        </div>

        <DragOverlay dropAnimation={null}>
          {activeContact ? (
            <div className="w-[224px] shadow-xl rotate-1 opacity-90 pointer-events-none">
              <ContactCardContent contact={activeContact} />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}
