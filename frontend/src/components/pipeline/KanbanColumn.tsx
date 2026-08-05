import { useDroppable } from "@dnd-kit/core";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatMXN, type PipelineDeal, type PipelineStage } from "@/lib/queries/pipeline";
import { DealCard } from "./DealCard";

interface Props {
  stage: PipelineStage;
  allStages: PipelineStage[];
  deals: PipelineDeal[];
  contactName: (id: string | null) => string | undefined;
  contactColor: (id: string | null) => string | null | undefined;
  contactLastActivityAt: (id: string | null) => string | null | undefined;
  onOpenDeal: (deal: PipelineDeal) => void;
  onAddDeal: (stage: PipelineStage) => void;
  onRequestLost: (deal: PipelineDeal) => void;
  wipLimit?: number;
}

export function KanbanColumn({
  stage, allStages, deals, contactName, contactColor, contactLastActivityAt,
  onOpenDeal, onAddDeal, onRequestLost, wipLimit = 10,
}: Props) {
  // La COLUMNA ENTERA es la zona droppable (no solo la lista de tarjetas).
  const { setNodeRef, isOver } = useDroppable({ id: stage.id, data: { stage } });
  const total = deals.reduce((s, d) => s + d.amount, 0);
  const isActive = !stage.isWon && !stage.isLost;
  const overWip = isActive && deals.length > wipLimit;

  return (
    <div
      ref={setNodeRef}
      className={cn(
        // h-full: ocupa todo el alto del board (definido por el contenedor padre).
        "flex flex-col h-full w-[85vw] max-w-[320px] md:w-[280px] shrink-0 rounded-xl border border-border bg-muted/30 transition-colors",
        overWip && "border-t-2 border-t-warning",
        isOver && "bg-primary/5 ring-1 ring-primary/40 ring-inset",
      )}
    >
      <div className="px-3 pt-3 pb-2 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: stage.color }} />
          <span className="text-sm font-semibold flex-1 truncate">{stage.name}</span>
          <span className="text-xs font-bold bg-background border border-border rounded-full px-1.5 py-0.5 min-w-[1.5rem] text-center">
            {deals.length}
          </span>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6"
            onClick={() => onAddDeal(stage)}
            aria-label={`Añadir oportunidad en ${stage.name}`}
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
        {overWip && (
          <span className="mt-1 inline-block text-[10px] font-semibold text-warning bg-warning/10 border border-warning/30 rounded-full px-1.5 py-0.5 leading-none">
            Cuello de botella
          </span>
        )}
      </div>

      {/* Lista de tarjetas: crece a todo el alto disponible (flex-1) y tiene SU PROPIO scroll. */}
      <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-2">
        {deals.map((d) => (
          <DealCard
            key={d.id}
            deal={d}
            stages={allStages}
            contactName={contactName(d.contactId)}
            contactColor={contactColor(d.contactId)}
            contactLastActivityAt={contactLastActivityAt(d.contactId)}
            onOpen={onOpenDeal}
            onRequestLost={onRequestLost}
          />
        ))}
        {deals.length === 0 ? (
          <div className="h-full min-h-[120px] grid place-items-center text-xs text-muted-foreground italic">
            Arrastra un deal aquí
          </div>
        ) : (
          <div className="min-h-[40px]" aria-hidden />
        )}
      </div>

      {/* Total fijo en el pie de la columna */}
      <div className="shrink-0 px-3 py-2 border-t border-border rounded-b-xl bg-muted/50">
        <span className="text-xs font-semibold text-foreground">{formatMXN(total)}</span>
      </div>
    </div>
  );
}
