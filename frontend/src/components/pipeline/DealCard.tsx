import { memo } from "react";
import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { useNavigate } from "react-router-dom";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { formatMXN, type PipelineDeal, type PipelineStage } from "@/lib/queries/pipeline";
import { computeDealHealth } from "@/lib/dealHealth";
import { HealthBadges } from "./HealthBadges";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { QuickActions } from "./QuickActions";

interface Props {
  deal: PipelineDeal;
  stages?: PipelineStage[];
  contactName?: string;
  contactColor?: string | null;
  contactLastActivityAt?: string | null;
  onOpen: (deal: PipelineDeal) => void;
  onRequestLost?: (deal: PipelineDeal) => void;
  isOverlay?: boolean;
}

function probabilityColor(p: number): string {
  if (p >= 70) return "bg-success";
  if (p >= 40) return "bg-warning";
  return "bg-danger";
}

function probabilityReason(p: number): string {
  if (p >= 70) return "Alta probabilidad de cierre.";
  if (p >= 40) return "Probabilidad media; mantén el seguimiento.";
  return "Baja probabilidad; requiere atención.";
}

function DealCardImpl({
  deal, stages, contactName, contactColor, contactLastActivityAt, onOpen, onRequestLost, isOverlay,
}: Props) {
  const navigate = useNavigate();
  const health = computeDealHealth(deal, contactLastActivityAt);

  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: deal.id,
    data: { deal },
  });

  const style = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging && !isOverlay ? 0.4 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => {
        if (isOverlay) return;
        onOpen(deal);
      }}
      className={cn(
        "relative cursor-pointer rounded-xl bg-card border border-border p-3 shadow-sm transition-all overflow-hidden group",
        !isOverlay && "hover:shadow-md hover:border-primary/30",
        isOverlay && "shadow-glow rotate-1",
      )}
    >
      {!isOverlay && onRequestLost && stages && (
        <QuickActions deal={deal} stages={stages} onRequestLost={onRequestLost} />
      )}

      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="font-semibold text-sm leading-tight line-clamp-2">{deal.name}</div>
      </div>

      <div className="text-success font-bold text-base mb-2">{formatMXN(deal.amount)} MXN</div>

      {contactName && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            if (deal.contactId) navigate(`/contacts/${deal.contactId}`); // TODO: ajusta a /leads/ si aplica
          }}
          className="inline-flex items-center gap-1.5 text-xs bg-muted hover:bg-muted/70 rounded-full pl-0.5 pr-2 py-0.5 max-w-full"
        >
          <Avatar className="h-4 w-4">
            <AvatarFallback
              className="text-[8px] text-white"
              style={{ backgroundColor: contactColor ?? "hsl(220 13% 65%)" }}
            >
              {contactName.split(" ").map((p) => p[0]).slice(0, 2).join("")}
            </AvatarFallback>
          </Avatar>
          <span className="truncate">{contactName}</span>
        </button>
      )}

      <div className="flex items-center justify-between gap-2 mt-3">
        <HealthBadges health={health} />
        <Avatar className="h-5 w-5">
          <AvatarFallback className="text-[9px] text-white" style={{ backgroundColor: deal.ownerColor }}>
            {deal.ownerInitials}
          </AvatarFallback>
        </Avatar>
      </div>

      {/* Probability progress bar at the bottom */}
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className="absolute left-0 right-0 bottom-0 h-1.5 bg-muted/50 cursor-help"
              onClick={(e) => e.stopPropagation()}
            >
              <div
                className={cn("h-full transition-all", probabilityColor(deal.probability))}
                style={{ width: `${deal.probability}%` }}
              />
            </div>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-[260px] text-xs">
            <div className="font-semibold mb-0.5">Probabilidad de cierre {deal.probability}%</div>
            <div className="text-muted-foreground leading-snug">{probabilityReason(deal.probability)}</div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

export const DealCard = memo(DealCardImpl);

/* FASE 2 (removido): QuickActions, sugerencias IA (Sparkles chip), useEntityUrgency (punto rojo),
   tareas pendientes (ClipboardList), unread (MessageCircle), selección múltiple (Checkbox),
   y el tooltip de probabilidad vía scoreDeal (reemplazado por explicación estática). */
