import { useState, useCallback, useMemo } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  pointerWithin,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, type OppCard } from "@/lib/api";
import { useOpportunityStore } from "../opportunityStore";
import { KanbanColumn } from "./KanbanColumn";
import { OpportunityCardContent } from "./OpportunityCard";
import { Skeleton } from "@/components/ui/skeleton";

export function OppKanbanBoard({
  onNewOpportunity,
}: {
  onNewOpportunity?: (stageId?: string) => void;
}) {
  const { stages, boardByStage, loading, error, optimisticMove, openDrawer } = useOpportunityStore();
  const [activeCard, setActiveCard] = useState<OppCard | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const handleDragStart = useCallback(({ active }: DragStartEvent) => {
    setActiveCard((active.data.current?.card as OppCard) ?? null);
  }, []);

  // Build stage map for quick lookup
  const stageMap = useMemo(
    () => new Map(stages.map((s) => [s.id, s])),
    [stages],
  );

  const handleDragEnd = useCallback(
    async ({ active, over }: DragEndEvent) => {
      setActiveCard(null);
      if (!over) return;

      const oppId = active.id as string;
      const toStageId = over.id as string;

      const toStage = stageMap.get(toStageId);
      if (!toStage) return;

      // Find from-stage
      let fromStageId: string | null = null;
      for (const [stageId, cards] of Object.entries(boardByStage)) {
        if (cards.some((c) => c.id === oppId)) {
          fromStageId = stageId;
          break;
        }
      }
      if (!fromStageId || fromStageId === toStageId) return;

      // Lost stage requires explicit reason modal (Prompt 4)
      if (toStage.is_lost) {
        toast.warning("Esta etapa requiere indicar el motivo de pérdida", {
          description: "Usa la acción 'Marcar como perdida' en la tarjeta.",
        });
        return;
      }

      // Optimistic move
      const revert = optimisticMove(oppId, toStageId);

      try {
        await api.moveOpportunityStage(oppId, toStageId);
        toast.success(`Oportunidad movida a "${toStage.name}"`);
      } catch (err) {
        revert();
        const msg = err instanceof Error ? err.message : "Error desconocido";
        if (msg.toLowerCase().includes("requires_reason") || msg.includes("422")) {
          toast.warning("Esta etapa requiere indicar el motivo de pérdida");
        } else {
          toast.error("Error al mover la oportunidad", { description: msg });
        }
      }
    },
    [stageMap, boardByStage, optimisticMove],
  );

  if (loading) {
    return (
      <div className="flex gap-3 pb-4" aria-busy="true" aria-label="Cargando tablero">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="w-[272px] shrink-0 rounded-xl border border-border bg-card/50 p-3 space-y-2"
          >
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
    );
  }

  if (stages.length === 0) {
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
      <div className="flex gap-3 pb-2 overflow-x-auto snap-x snap-mandatory scroll-smooth -mx-3 px-3 sm:h-full">
        {stages.map((stage) => (
          <KanbanColumn
            key={stage.id}
            stage={stage}
            cards={boardByStage[stage.id] ?? []}
            onAddNew={() => onNewOpportunity?.(stage.id)}
            onCardClick={openDrawer}
          />
        ))}
      </div>

      <DragOverlay dropAnimation={null}>
        {activeCard ? (
          <div
            className={cn(
              "w-[260px] shadow-xl rotate-1 opacity-90 pointer-events-none",
            )}
          >
            <OpportunityCardContent opp={activeCard} />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
