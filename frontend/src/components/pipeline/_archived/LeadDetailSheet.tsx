// Archivado en Etapa 3 — huérfano desde que ListView.tsx dejó de usarse.
// Contiene UI de score/sentiment/asignación de lead que DealDrawer.tsx no tiene hoy
// — útil como referencia si se decide enriquecer DealDrawer con esos datos.
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, UserCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAIBarStore } from "@/stores/aiBarStore";
import { LeadScoreGauge } from "@/components/leads/LeadScoreGauge";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { WBadge } from "@/components/walix/Badge";
import { StatusBadge } from "@/components/whatsapp/StatusBadge";
import { AssignmentDropdown } from "@/components/whatsapp/AssignmentDropdown";
import { useTenantLabels } from "@/hooks/useTenantLabels";

const SENTIMENT_LABELS: Record<string, string> = {
  neutral: "Neutral",
  interesado: "Interesado",
  urgente: "Urgente",
  negativo: "Negativo",
};

const SENTIMENT_VARIANT: Record<string, "neutral" | "info" | "danger" | "warning"> = {
  neutral: "neutral",
  interesado: "info",
  urgente: "danger",
  negativo: "warning",
};

interface Props {
  leadId: string | null;
  stageName?: string;
  stageColor?: string | null;
  onClose: () => void;
}

export function LeadDetailSheet({ leadId, stageName, stageColor, onClose }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const aiBar = useAIBarStore();
  const { entity } = useTenantLabels();
  const notifiedLeads = useRef<Set<string>>(new Set());

  const { data: lead, isLoading } = useQuery({
    queryKey: ["lead", leadId],
    queryFn: () => api.getLead(leadId!),
    enabled: Boolean(leadId),
    staleTime: 30_000,
  });

  const { data: scoreData } = useQuery({
    queryKey: ["lead-score", leadId],
    queryFn: () => api.getLeadScore(leadId!),
    enabled: Boolean(leadId),
    staleTime: 60_000,
  });

  // Trigger AI message once per lead when score >= 70
  useEffect(() => {
    if (!leadId || !scoreData?.current_score) return;
    if (scoreData.current_score >= 70 && !notifiedLeads.current.has(leadId)) {
      notifiedLeads.current.add(leadId);
      aiBar.addMessage(
        "assistant",
        `Este lead tiene ${scoreData.current_score}% de probabilidad de cierre. ¿Quieres que prepare una propuesta personalizada?`,
        ["Preparar propuesta"],
      );
      aiBar.setOpen(true);
    }
  }, [scoreData?.current_score, leadId]);

  const handoffMutation = useMutation({
    mutationFn: () => api.handoff(leadId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
      toast.success("Tomaste control de la conversación");
    },
    onError: (e: Error) => toast.error("Error al tomar control", { description: e.message }),
  });

  return (
    <Sheet open={Boolean(leadId)} onOpenChange={(v) => !v && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-[380px] flex flex-col p-0">
        {/* Stage color strip */}
        {stageColor && (
          <div className="h-1 w-full shrink-0" style={{ backgroundColor: stageColor }} />
        )}

        <SheetHeader className="px-4 py-3 border-b border-border shrink-0">
          <SheetTitle className="text-base leading-snug">
            {isLoading ? (
              <Skeleton className="h-5 w-40" />
            ) : (
              (lead?.name ?? lead?.wa_phone ?? entity)
            )}
          </SheetTitle>
          {stageName && (
            <p className="text-xs text-muted-foreground">{stageName}</p>
          )}
        </SheetHeader>

        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          ) : lead ? (
            <>
              {/* Badges */}
              <div className="flex items-center gap-2 flex-wrap">
                <StatusBadge status={lead.status} />
                <WBadge variant={SENTIMENT_VARIANT[lead.sentiment] ?? "neutral"}>
                  {SENTIMENT_LABELS[lead.sentiment] ?? lead.sentiment}
                </WBadge>
                {lead.qualification_score != null && (
                  <WBadge variant="brand">
                    {Math.round(lead.qualification_score * 100)}%
                  </WBadge>
                )}
              </div>

              {/* Key details */}
              <div className="text-xs text-muted-foreground space-y-1.5">
                <p>📱 {lead.wa_phone}</p>
                {lead.assigned_to_name && <p>👤 {lead.assigned_to_name}</p>}
                {lead.source && <p>📌 Fuente: {lead.source}</p>}
              </div>

              {/* Assignment */}
              <section>
                <h3 className={cn(
                  "text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2"
                )}>
                  Asignación
                </h3>
                <AssignmentDropdown lead={lead} />
              </section>

              {/* Quick actions */}
              <section className="space-y-2">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Acciones rápidas
                </h3>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start gap-2 h-9 text-xs"
                  onClick={() => handoffMutation.mutate()}
                  disabled={handoffMutation.isPending}
                >
                  <UserCheck className="h-3.5 w-3.5" />
                  Tomar control
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start gap-2 h-9 text-xs"
                  onClick={() => {
                    onClose();
                    navigate(`/whatsapp?leadId=${lead.id}`);
                  }}
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  Ver conversación completa
                </Button>
              </section>

              {/* Predicción de cierre */}
              <section>
                <h3 className={cn(
                  "text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3"
                )}>
                  Predicción de cierre
                </h3>
                <LeadScoreGauge leadId={lead.id} />
              </section>
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
