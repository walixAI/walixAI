import { useState } from "react";
import {
  DndContext, DragOverlay, KeyboardSensor, PointerSensor,
  useSensor, useSensors, type DragEndEvent, type DragStartEvent,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { toast } from "sonner";
import {
  formatMXN, useUpdateDealStage,
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
        onSuccess: () => toast.success(`Oportunidad movida a "${stage.name}"`),
        onError: () => toast.error("No se pudo mover la oportunidad"),
      },
    );
  }

  const totalPipeline = deals.reduce((s, d) => s + d.amount, 0);

  return (
    <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
      {/* Contenedor del board con ALTURA FIJA relativa al viewport.
          Ajusta el sustraendo (260px) si tu layout tiene más/menos chrome arriba. */}
      <div className="flex flex-col h-[calc(100vh-260px)] min-h-[420px]">
        {/* Carril de columnas: scroll HORIZONTAL aquí; el vertical vive dentro de cada columna. */}
        <div className="flex-1 min-h-0 flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
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
            />
          ))}
        </div>

        {/* Footer de totales por etapa (no se desplaza con el scroll vertical de las columnas). */}
        <div className="shrink-0 -mx-6 px-6 py-2 bg-slate-800 text-white border-t border-slate-700 mt-2">
          <div className="flex gap-3 overflow-x-auto items-center">
            {stages.map((stage) => {
              const total = deals.filter((d) => d.stageId === stage.id).reduce((s, d) => s + d.amount, 0);
              return (
                <div key={stage.id} className="w-[280px] shrink-0 text-xs">
                  <span className="text-slate-400">{stage.name}: </span>
                  <span className="font-semibold">{formatMXN(total)}</span>
                </div>
              );
            })}
            <div className="ml-auto pl-4 border-l border-slate-600 text-sm font-bold whitespace-nowrap">
              Total pipeline: {formatMXN(totalPipeline)}
            </div>
          </div>
        </div>
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
