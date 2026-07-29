import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useAIBarStore } from "@/stores/aiBarStore";
import { cn } from "@/lib/utils";

const URGENCY_BORDER: Record<string, string> = {
  high: "border-destructive bg-destructive/5",
  medium: "border-warning bg-warning/5",
  low: "border-primary/40 bg-primary/5",
};

const URGENCY_DOT: Record<string, string> = {
  high: "bg-destructive",
  medium: "bg-warning",
  low: "bg-primary",
};

interface Props {
  contactId: string;
  activitiesTotal: number;
}

export function FirstContactAIBanner({ contactId, activitiesTotal }: Props) {
  const { setDraftInput, setOpen } = useAIBarStore();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai-insight", "lead", contactId],
    queryFn: () => api.getContextInsight("lead", undefined, contactId),
    staleTime: 2 * 60 * 1_000,
    retry: false,
    enabled: activitiesTotal === 0,
  });

  // Only show for contacts with no activity yet
  if (activitiesTotal !== 0) return null;
  if (isError || isLoading || !data) return null;

  function handleAction(action: string) {
    setDraftInput(action);
    setOpen(true);
  }

  return (
    <div
      className={cn(
        "rounded-xl border p-4 mb-4 flex flex-col gap-2.5",
        URGENCY_BORDER[data.urgency] ?? "border-primary/40 bg-primary/5",
      )}
    >
      <div className="flex items-start gap-2.5">
        <Sparkles className="h-4 w-4 text-primary shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-primary">Walix AI</span>
            <span
              className={cn(
                "inline-block h-1.5 w-1.5 rounded-full",
                URGENCY_DOT[data.urgency] ?? "bg-primary",
              )}
            />
            <span className="text-xs text-muted-foreground capitalize">{data.urgency}</span>
          </div>
          <p className="text-sm text-foreground leading-snug">{data.insight}</p>
        </div>
      </div>

      {data.suggested_actions.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-7">
          {data.suggested_actions.map((action, i) => (
            <button
              key={i}
              onClick={() => handleAction(action)}
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs
                         bg-primary/15 text-primary border border-primary/30
                         hover:bg-primary/25 transition-colors text-left"
            >
              {action}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
