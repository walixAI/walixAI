import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAIBarStore } from "@/stores/aiBarStore";
import { AgentSuggestionCard } from "./AgentSuggestionCard";
import { Skeleton } from "@/components/ui/skeleton";

export function AgentSuggestionsPanel() {
  const setPendingSuggestionsCount = useAIBarStore((s) => s.setPendingSuggestionsCount);

  const { data, isLoading } = useQuery({
    queryKey: ["agent-suggestions"],
    queryFn: () => api.getAgentSuggestions(),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const pending = data?.filter((s) => ["suggested", "accepted"].includes(s.status)) ?? [];

  useEffect(() => {
    setPendingSuggestionsCount(pending.length);
  }, [pending.length, setPendingSuggestionsCount]);

  if (isLoading) {
    return (
      <div className="mx-4 mt-3 space-y-2">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  if (!data || data.length === 0) return null;

  return (
    <div className="mx-4 mt-3">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60 mb-2">
        Sugerencias del agente
      </p>
      {pending.length === 0 ? (
        <p className="text-xs text-muted-foreground italic">No hay sugerencias pendientes.</p>
      ) : (
        <div className="space-y-2">
          {pending.map((s) => (
            <AgentSuggestionCard key={s.id} suggestion={s} compact />
          ))}
        </div>
      )}
    </div>
  );
}
