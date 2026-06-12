import { useQuery } from "@tanstack/react-query";
import { Plus, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentSuggestionCard } from "@/components/agents/AgentSuggestionCard";
import { api, type AgentSuggestion } from "@/lib/api";

interface ContactRightPanelProps {
  contactId: string;
}

export function ContactRightPanel({ contactId }: ContactRightPanelProps) {
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

        <div className="rounded-xl border border-dashed border-border bg-muted/30 p-4 flex flex-col items-center text-center gap-1.5">
          <TrendingUp className="h-5 w-5 text-muted-foreground" />
          <p className="text-xs text-muted-foreground">Sin oportunidades activas.</p>
          <Button variant="link" size="sm" className="h-auto p-0 text-xs">
            + Crear oportunidad
          </Button>
        </div>
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
