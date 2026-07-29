import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type BoardLeadCard } from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const SENTIMENT_DOT: Record<string, string> = {
  interesado: "🟢",
  neutral: "🟡",
  urgente: "🔴",
  negativo: "🔴",
};

export function ListView({
  branchId,
  advisorId,
  onLeadClick,
}: {
  branchId: string;
  advisorId: string | null;
  onLeadClick: (card: BoardLeadCard, stageName: string, stageColor: string | null) => void;
}) {
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["pipeline-board", branchId],
    queryFn: () => api.getPipelineBoard(branchId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled: Boolean(branchId),
  });

  const moveMutation = useMutation({
    mutationFn: ({ leadId, stageId }: { leadId: string; stageId: string }) =>
      api.moveLeadToStage(leadId, stageId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipeline-board", branchId] });
      toast.success("Lead movido correctamente");
    },
    onError: (e: Error) => toast.error("Error al mover lead", { description: e.message }),
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-80" />
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-12 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError || !data || data.stages.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">Sin datos de pipeline.</p>
      </div>
    );
  }

  const stageOptions = data.stages.map((s) => ({ id: s.id, name: s.name }));

  return (
    <Tabs defaultValue={data.stages[0].id}>
      {/* Tab triggers */}
      <TabsList className="mb-4 flex flex-wrap h-auto gap-1.5 bg-transparent p-0">
        {data.stages.map((stage) => {
          const count = advisorId
            ? stage.leads.filter((l) => l.assigned_to === advisorId).length
            : stage.total;
          return (
            <TabsTrigger
              key={stage.id}
              value={stage.id}
              className={cn(
                "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-border",
                "data-[state=active]:bg-primary data-[state=active]:text-primary-foreground",
                "data-[state=active]:border-primary",
              )}
            >
              <span
                className="h-2 w-2 rounded-full shrink-0"
                style={{ backgroundColor: stage.color ?? "#6366f1" }}
              />
              {stage.name}
              <span className="text-[10px] opacity-70">{count}</span>
            </TabsTrigger>
          );
        })}
      </TabsList>

      {/* Tab panels */}
      {data.stages.map((stage) => {
        const leads = advisorId
          ? stage.leads.filter((l) => l.assigned_to === advisorId)
          : stage.leads;

        return (
          <TabsContent key={stage.id} value={stage.id}>
            {leads.length === 0 ? (
              <div className="flex items-center justify-center py-16">
                <p className="text-sm text-muted-foreground">Sin leads en esta etapa.</p>
              </div>
            ) : (
              <div className="rounded-xl border border-border overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/30">
                      <th className="text-left text-xs font-semibold text-muted-foreground px-4 py-2.5">
                        Nombre
                      </th>
                      <th className="text-left text-xs font-semibold text-muted-foreground px-4 py-2.5">
                        Sentimiento
                      </th>
                      <th className="text-left text-xs font-semibold text-muted-foreground px-4 py-2.5">
                        Días
                      </th>
                      <th className="text-left text-xs font-semibold text-muted-foreground px-4 py-2.5">
                        Asesor
                      </th>
                      <th className="text-left text-xs font-semibold text-muted-foreground px-4 py-2.5">
                        Mover a
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {leads.map((card) => (
                      <tr
                        key={card.id}
                        onClick={() => onLeadClick(card, stage.name, stage.color)}
                        className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors cursor-pointer"
                      >
                        {/* Nombre */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span
                              className="inline-flex items-center justify-center h-6 w-6 rounded-full
                                         bg-primary/10 text-primary text-[10px] font-bold shrink-0"
                            >
                              {(card.name ?? card.wa_phone).charAt(0).toUpperCase()}
                            </span>
                            <span className="font-medium truncate max-w-[160px]">
                              {card.name ?? card.wa_phone}
                            </span>
                          </div>
                        </td>

                        {/* Sentimiento */}
                        <td className="px-4 py-3">
                          <span className="flex items-center gap-1.5">
                            <span className="text-sm leading-none">
                              {SENTIMENT_DOT[card.sentiment] ?? "🟡"}
                            </span>
                            <span className="text-xs text-muted-foreground capitalize">
                              {card.sentiment}
                            </span>
                          </span>
                        </td>

                        {/* Días en etapa */}
                        <td className="px-4 py-3 text-xs tabular-nums text-muted-foreground">
                          {card.days_in_stage}d
                        </td>

                        {/* Asesor */}
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          <span className="truncate max-w-[120px] block">
                            {card.assigned_to_name ?? "—"}
                          </span>
                        </td>

                        {/* Stage select — stops propagation so row click doesn't fire */}
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <Select
                            value={stage.id}
                            onValueChange={(targetStageId) => {
                              if (targetStageId !== stage.id) {
                                moveMutation.mutate({
                                  leadId: card.id,
                                  stageId: targetStageId,
                                });
                              }
                            }}
                            disabled={moveMutation.isPending}
                          >
                            <SelectTrigger className="h-7 w-36 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {stageOptions.map((opt) => (
                                <SelectItem
                                  key={opt.id}
                                  value={opt.id}
                                  className="text-xs"
                                >
                                  {opt.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>
        );
      })}
    </Tabs>
  );
}
