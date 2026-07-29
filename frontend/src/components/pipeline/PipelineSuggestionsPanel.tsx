import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { AgentSuggestionCard } from "@/components/agents/AgentSuggestionCard";

export function PipelineSuggestionsPanel() {
  const { data: all = [] } = useQuery({
    queryKey: ["agent-suggestions"],
    queryFn: () => api.getAgentSuggestions(),
    staleTime: 60_000,
  });

  const suggestions = all.filter(
    (s) => s.agent_type === "pipeline" && s.status === "suggested",
  );

  if (suggestions.length === 0) return null;

  const visible = suggestions.slice(0, 5);
  const extraCount = suggestions.length - 5;

  return (
    <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-primary shrink-0" />
        <p className="text-sm font-semibold text-primary">Sugerencias de IA para tu pipeline</p>
      </div>

      <div className="space-y-2">
        {visible.map((s) => (
          <AgentSuggestionCard key={s.id} suggestion={s} />
        ))}
        {extraCount > 0 && (
          <button className="w-full text-center text-xs text-primary hover:underline py-1">
            Ver {extraCount} más
          </button>
        )}
      </div>
    </div>
  );
}
