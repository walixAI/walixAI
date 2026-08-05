import { useState } from "react";
import { useTenantLabels } from "@/hooks/useTenantLabels";
import {
  DndContext, DragOverlay, KeyboardSensor, PointerSensor,
  useSensor, useSensors, type DragEndEvent, type DragStartEvent,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { toast } from "sonner";
import {
  useUpdateDealStage,
  type PipelineDeal, type PipelineStage,
} from "@/lib/queries/pipeline";
import { KanbanColumn } from "./KanbanColumn";
import { DealCard } from "./DealCard";

interface Props {
  stages: PipelineStage[];
  deals: PipelineDeal[];
  contactName: (id: string | null) => string | undefined;
  contactColor: (id: string | null) => string | null | undefined;
  contactLastActivityAt: (id: string | null) => string | null | undefined;
  onOpenDeal: (deal: PipelineDeal) => void;
  onAddDeal: (stage: PipelineStage) => void;
  onRequestLost: (deal: PipelineDeal) => void;
}

export function KanbanBoard(props: Props) {
  const { deal } = useTenantLabels();
  const { stages, deals } = props;
  const [active, setActive] = useState<PipelineDeal | null>(null);
  const update = useUpdateDealStage();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function onDragStart(e: DragStartEvent) {
    const deal = deals.find((d) => d.id === e.active.id);
    if (deal) setActive(deal);
  }

  function onDragEnd(e: DragEndEvent) {
    setActive(null);
    const dealId = e.active.id as string;
    const targetStageId = e.over?.id as string | undefined;
    if (!targetStageId) return;
    const deal = deals.find((d) => d.id === dealId);
    const stage = stages.find((s) => s.id === targetStageId);
    if (!deal || !stage) return;
    if (deal.stageId === stage.id) return;
    // Si destino es "Cerrado Perdido", abre el modal y NO mueve aún
    if (stage.isLost) {
      props.onRequestLost(deal);
      return;
    }
    update.mutate(
      { dealId, stage },
      {
        onSuccess: () => toast.success(`${deal} movida a "${stage.name}"`),
        onError: () => toast.error(`No se pudo mover la ${deal.toLowerCase()}`),
      },
    );
  }

  return (
    <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
      <div className="h-[calc(100vh-260px)] min-h-[420px] flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
        {stages.map((stage) => (
          <KanbanColumn
            key={stage.id}
            stage={stage}
            allStages={stages}
            deals={deals.filter((d) => d.stageId === stage.id)}
            contactName={props.contactName}
            contactColor={props.contactColor}
            contactLastActivityAt={props.contactLastActivityAt}
            onOpenDeal={props.onOpenDeal}
            onAddDeal={props.onAddDeal}
            onRequestLost={props.onRequestLost}
          />
        ))}
      </div>

      <DragOverlay>
        {active && (
          <div className="w-[260px]">
            <DealCard
              deal={active}
              contactName={props.contactName(active.contactId)}
              contactColor={props.contactColor(active.contactId)}
              contactLastActivityAt={props.contactLastActivityAt(active.contactId)}
              onOpen={() => {}}
              isOverlay
            />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
