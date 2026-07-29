import { useQuery } from "@tanstack/react-query";
import { Plus, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentSuggestionCard } from "@/components/agents/AgentSuggestionCard";
import { api, type AgentSuggestion, type DealSummary } from "@/lib/api";

function formatMXN(n: number): string {
  if (!n) return "";
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n);
}

interface ContactRightPanelProps {
  contactId: string;
}

export function ContactRightPanel({ contactId }: ContactRightPanelProps) {
  const { data: dealsData } = useQuery({
    queryKey: ["contact-deals", contactId],
    queryFn: () => api.getDealsByLead(contactId),
    staleTime: 60_000,
  });

  const deals: DealSummary[] = dealsData?.items ?? [];
  const visibleDeals = deals.slice(0, 3);
  const extraDealsCount = deals.length - 3;
  const totalPipelineValue = deals.reduce((sum, d) => sum + (d.amount ?? 0), 0);

  const { data: allSuggestions = [] } = useQuery({
    queryKey: ["agent-suggestions"],
    queryFn: () => api.getAgentSuggestions(),
    staleTime: 60_000,
  });

  const suggestions: AgentSuggestion[] = allSuggestions.filter(
    (s) =>
      s.status === "suggested" &&
      (s.action_payload?.lead_id as string | undefined) === contactId,
  );

  const visibleSuggestions = suggestions.slice(0, 3);
  const extraCount = suggestions.length - 3;

  return (
    <div className="p-4 space-y-5">
      {/* Deals section */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Oportunidades
          </p>
          <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px] gap-0.5">
            <Plus className="h-3 w-3" />
            Nueva
          </Button>
        </div>

        {deals.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-muted/30 p-4 flex flex-col items-center text-center gap-1.5">
            <TrendingUp className="h-5 w-5 text-muted-foreground" />
            <p className="text-xs text-muted-foreground">Sin oportunidades activas.</p>
            <Button variant="link" size="sm" className="h-auto p-0 text-xs">
              + Crear oportunidad
            </Button>
          </div>
        ) : (
          <div className="space-y-1.5">
            {totalPipelineValue > 0 && (
              <div className="flex items-center justify-between px-1 pb-1 border-b border-border">
                <span className="text-[10px] text-muted-foreground">Valor total en pipeline</span>
                <span className="text-xs font-semibold text-foreground">{formatMXN(totalPipelineValue)}</span>
              </div>
            )}
            {visibleDeals.map((deal) => (
              <div
                key={deal.id}
                className="rounded-lg border border-border bg-card px-3 py-2 space-y-0.5"
              >
                <p className="text-xs font-medium truncate">{deal.title}</p>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    {deal.amount ? formatMXN(deal.amount) : "—"}
                  </span>
                  {deal.probability > 0 && (
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">
                      {deal.probability}%
                    </span>
                  )}
                </div>
              </div>
            ))}
            {extraDealsCount > 0 && (
              <button className="w-full text-center text-xs text-primary hover:underline py-1">
                Ver {extraDealsCount} más
              </button>
            )}
          </div>
        )}
      </div>

      {/* AI suggestions */}
      {visibleSuggestions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Sugerencias IA
          </p>
          {visibleSuggestions.map((s) => (
            <AgentSuggestionCard key={s.id} suggestion={s} compact />
          ))}
          {extraCount > 0 && (
            <button className="w-full text-center text-xs text-primary hover:underline py-1">
              Ver {extraCount} más
            </button>
          )}
        </div>
      )}
    </div>
  );
}
