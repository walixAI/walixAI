import { useNavigate } from "react-router-dom";
import { MessageCircle, Trophy, XCircle } from "lucide-react";
import { toast } from "sonner";
import { useUpdateDealStage, type PipelineDeal, type PipelineStage } from "@/lib/queries/pipeline";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface Props {
  deal: PipelineDeal;
  stages: PipelineStage[];
  onRequestLost: (deal: PipelineDeal) => void;
}

export function QuickActions({ deal, stages, onRequestLost }: Props) {
  const navigate = useNavigate();
  const updateStage = useUpdateDealStage();

  if (deal.isWon || deal.isLost) return null;

  const wonStage = stages.find((s) => s.isWon) ?? null;

  function handleWhatsApp(e: React.MouseEvent) {
    e.stopPropagation();
    navigate(`/whatsapp?leadId=${deal.contactId}`);
  }

  function handleWon(e: React.MouseEvent) {
    e.stopPropagation();
    if (!wonStage) return;
    updateStage.mutate(
      { dealId: deal.id, stage: wonStage },
      {
        onSuccess: () => toast.success(`"${deal.name}" marcada como ganada 🎉`),
        onError: () => toast.error("No se pudo marcar como ganada"),
      },
    );
  }

  function handleLost(e: React.MouseEvent) {
    e.stopPropagation();
    onRequestLost(deal);
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10"
        // stopPropagation on the container prevents any missed click from bubbling to onOpen
        onClick={(e) => e.stopPropagation()}
      >
        {deal.contactId && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={handleWhatsApp}
                className="rounded-lg p-1.5 bg-background/90 backdrop-blur border border-border text-muted-foreground hover:bg-primary/10 hover:text-primary hover:border-primary/30 transition-colors"
                aria-label="Ir a WhatsApp"
              >
                <MessageCircle className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="text-xs">WhatsApp</TooltipContent>
          </Tooltip>
        )}

        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={handleWon}
              disabled={!wonStage || updateStage.isPending}
              className="rounded-lg p-1.5 bg-background/90 backdrop-blur border border-border text-muted-foreground hover:bg-success/10 hover:text-success hover:border-success/30 transition-colors disabled:opacity-50"
              aria-label="Marcar ganado"
            >
              <Trophy className="h-3.5 w-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">Marcar ganado</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={handleLost}
              className="rounded-lg p-1.5 bg-background/90 backdrop-blur border border-border text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
              aria-label="Marcar perdido"
            >
              <XCircle className="h-3.5 w-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs">Marcar perdido</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}
