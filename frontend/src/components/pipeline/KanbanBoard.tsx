import { useState, useMemo, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
import {
  api,
  type BoardLeadCard,
  type BoardResponse,
  type PipelineStageBoardOut,
} from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

const SENTIMENT_DOT: Record<string, string> = {
  interesado: "🟢",
  neutral: "🟡",
  urgente: "🔴",
  negativo: "🔴",
};

// ── Pure visual card ──────────────────────────────────────────────────────────

function LeadCardContent({ card }: { card: BoardLeadCard }) {
  const initial = (card.name ?? card.wa_phone).charAt(0).toUpperCase();
  const displayName = card.name ?? card.wa_phone;

  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2.5 space-y-2 w-full pointer-events-none">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center justify-center h-7 w-7 rounded-full
                         bg-primary/10 text-primary text-xs font-bold shrink-0">
          {initial}
        </span>
        <p className="text-sm font-medium truncate flex-1">{displayName}</p>
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs leading-none">{SENTIMENT_DOT[card.sentiment] ?? "🟡"}</span>
        <span className="text-[10px] text-muted-foreground capitalize">{card.sentiment}</span>
        {card.risk_score != null && card.risk_score > 0.7 && (
          <span className="ml-auto inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full
                           text-[10px] font-medium bg-destructive/10 text-destructive border border-destructive/20">
            ⚠ Riesgo
          </span>
        )}
      </div>

      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span>{card.days_in_stage}d en etapa</span>
        {card.assigned_to_name && (
          <span className="truncate max-w-[90px]">{card.assigned_to_name}</span>
        )}
      </div>
    </div>
  );
}

// ── Draggable card ────────────────────────────────────────────────────────────

function DraggableLeadCard({
  card,
  onClick,
}: {
  card: BoardLeadCard;
  onClick: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: card.id,
    data: { card },
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
      <LeadCardContent card={card} />
    </div>
  );
}

// ── Droppable column ──────────────────────────────────────────────────────────

function KanbanColumn({
  stage,
  advisorId,
  onLeadClick,
}: {
  stage: PipelineStageBoardOut;
  advisorId: string | null;
  onLeadClick: (card: BoardLeadCard) => void;
}) {
  const { isOver, setNodeRef } = useDroppable({ id: stage.id });

  const leads = useMemo(
    () =>
      advisorId
        ? stage.leads.filter((l) => l.assigned_to === advisorId)
        : stage.leads,
    [stage.leads, advisorId],
  );

  return (
    <div className="w-[260px] shrink-0 flex flex-col rounded-xl border border-border bg-card/50">
      {/* Colored top strip */}
      <div
        className="h-1 rounded-t-xl shrink-0"
        style={{ backgroundColor: stage.color ?? "#6366f1" }}
      />

      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <span className="text-sm font-semibold truncate flex-1">{stage.name}</span>
        <span
          className={cn(
            "text-xs font-medium tabular-nums px-1.5 py-0.5 rounded-full shrink-0",
            leads.length > 0
              ? "bg-primary/10 text-primary"
              : "bg-muted text-muted-foreground",
          )}
        >
          {leads.length}
        </span>
      </div>

      {/* Drop zone */}
      <div
        ref={setNodeRef}
        className={cn(
          "flex-1 overflow-y-auto p-2 space-y-2 min-h-[120px] rounded-b-xl transition-colors duration-150",
          isOver && "bg-primary/5",
        )}
      >
        {leads.length === 0 ? (
          <p className="text-[11px] text-muted-foreground text-center py-8 select-none">
            Sin leads
          </p>
        ) : (
          leads.map((card) => (
            <DraggableLeadCard
              key={card.id}
              card={card}
              onClick={() => onLeadClick(card)}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── Board ─────────────────────────────────────────────────────────────────────

export function KanbanBoard({
  branchId,
  advisorId,
  onLeadClick,
}: {
  branchId: string;
  advisorId: string | null;
  onLeadClick: (card: BoardLeadCard, stageName: string, stageColor: string | null) => void;
}) {
  const qc = useQueryClient();
  const [activeCard, setActiveCard] = useState<BoardLeadCard | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["pipeline-board", branchId],
    queryFn: () => api.getPipelineBoard(branchId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled: Boolean(branchId),
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const handleDragStart = useCallback(({ active }: DragStartEvent) => {
    setActiveCard((active.data.current?.card as BoardLeadCard) ?? null);
  }, []);

  const handleDragEnd = useCallback(
    ({ active, over }: DragEndEvent) => {
      setActiveCard(null);
      if (!over) return;

      const cardId = active.id as string;
      const targetStageId = over.id as string;

      const sourceStage = data?.stages.find((s) => s.leads.some((l) => l.id === cardId));
      if (!sourceStage || sourceStage.id === targetStageId) return;

      const snapshot = qc.getQueryData<BoardResponse>(["pipeline-board", branchId]);

      // Optimistic: move card in cache immediately
      qc.setQueryData<BoardResponse>(["pipeline-board", branchId], (old) => {
        if (!old) return old;
        let movedCard: BoardLeadCard | undefined;
        const stages = old.stages.map((stage) => {
          const filtered = stage.leads.filter((l) => {
            if (l.id === cardId) {
              movedCard = l;
              return false;
            }
            return true;
          });
          return { ...stage, leads: filtered, total: filtered.length };
        });
        if (movedCard) {
          const idx = stages.findIndex((s) => s.id === targetStageId);
          if (idx >= 0) {
            const updated = [...stages[idx].leads, movedCard];
            stages[idx] = { ...stages[idx], leads: updated, total: updated.length };
          }
        }
        return { stages };
      });

      api.moveLeadToStage(cardId, targetStageId).catch((e: Error) => {
        if (snapshot) qc.setQueryData(["pipeline-board", branchId], snapshot);
        toast.error("Error al mover lead", { description: e.message });
      });
    },
    [data, branchId, qc],
  );

  if (isLoading) {
    return (
      <div className="flex gap-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="w-[260px] shrink-0 rounded-xl border border-border bg-card/50 p-3 space-y-2"
          >
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">Error al cargar el pipeline.</p>
      </div>
    );
  }

  if (data.stages.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">
          Sin etapas configuradas en este pipeline.
        </p>
      </div>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={pointerWithin}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-3 h-full pb-2">
        {data.stages.map((stage) => (
          <KanbanColumn
            key={stage.id}
            stage={stage}
            advisorId={advisorId}
            onLeadClick={(card) => onLeadClick(card, stage.name, stage.color)}
          />
        ))}
      </div>

      <DragOverlay dropAnimation={null}>
        {activeCard ? (
          <div className="w-[244px] shadow-xl rotate-1 opacity-90 pointer-events-none">
            <LeadCardContent card={activeCard} />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
