import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, Search, Target, Settings, RefreshCw, Check, X } from "lucide-react";
import { toast } from "sonner";
import { api, AgentSuggestion } from "@/lib/api";
import { cn } from "@/lib/utils";

const TYPE_ICON: Record<string, React.ReactNode> = {
  follow_up: <Bell className="h-3.5 w-3.5" />,
  analysis: <Search className="h-3.5 w-3.5" />,
  closure: <Target className="h-3.5 w-3.5" />,
  cierre: <Target className="h-3.5 w-3.5" />,
  config: <Settings className="h-3.5 w-3.5" />,
};

const TYPE_EMOJI: Record<string, string> = {
  follow_up: "🔔",
  analysis: "🔍",
  closure: "🎯",
  cierre: "🎯",
  config: "⚙️",
};

function getEmoji(type: string): string {
  return TYPE_EMOJI[type] ?? "⚙️";
}

function getIcon(type: string): React.ReactNode {
  return TYPE_ICON[type] ?? <Settings className="h-3.5 w-3.5" />;
}

function ExpiresIn({ expiresAt }: { expiresAt: string }) {
  const ms = new Date(expiresAt).getTime() - Date.now();
  const hours = Math.floor(ms / 3_600_000);
  if (hours < 0) return <span className="text-[10px] text-danger font-medium">Expirada</span>;
  if (hours < 24) return <span className="text-[10px] text-warning font-medium">Expira en {hours}h</span>;
  const days = Math.floor(hours / 24);
  return <span className="text-[10px] text-muted-foreground">Expira en {days}d</span>;
}

interface Props {
  suggestion: AgentSuggestion;
  compact?: boolean;
}

export function AgentSuggestionCard({ suggestion, compact = false }: Props) {
  const qc = useQueryClient();
  const isDone = !["suggested", "accepted"].includes(suggestion.status);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["agent-suggestions"] });
    qc.invalidateQueries({ queryKey: ["automations"] });
  };

  const confirmMutation = useMutation({
    mutationFn: () => api.confirmSuggestion(suggestion.id),
    onSuccess: () => { toast.success("Sugerencia confirmada"); invalidate(); },
    onError: (e: Error) => toast.error("Error al confirmar", { description: e.message }),
  });

  const dismissMutation = useMutation({
    mutationFn: () => api.dismissSuggestion(suggestion.id),
    onSuccess: () => { invalidate(); },
    onError: (e: Error) => toast.error("Error al descartar", { description: e.message }),
  });

  const isPending = confirmMutation.isPending || dismissMutation.isPending;

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card/60 p-3 space-y-2 transition-opacity",
        isDone && "opacity-50",
      )}
    >
      <div className="flex items-start gap-2">
        <span className="shrink-0 text-base leading-none mt-0.5">
          {getEmoji(suggestion.agent_type)}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium leading-snug text-foreground line-clamp-3">
            {suggestion.suggestion_text}
          </p>
          {!compact && suggestion.trigger_description && (
            <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-1">
              {suggestion.trigger_description}
            </p>
          )}
        </div>
        <ExpiresIn expiresAt={suggestion.expires_at} />
      </div>

      {!isDone && (
        <div className="flex gap-1.5 pt-0.5">
          <button
            onClick={() => confirmMutation.mutate()}
            disabled={isPending}
            className="flex-1 flex items-center justify-center gap-1 rounded-lg
                       bg-primary/15 text-primary hover:bg-primary/25 text-[11px] font-medium
                       py-1.5 transition-colors disabled:opacity-50"
          >
            {confirmMutation.isPending
              ? <RefreshCw className="h-3 w-3 animate-spin" />
              : <Check className="h-3 w-3" />}
            Confirmar
          </button>
          <button
            onClick={() => dismissMutation.mutate()}
            disabled={isPending}
            className="flex items-center justify-center gap-1 rounded-lg
                       text-muted-foreground hover:text-foreground hover:bg-muted text-[11px]
                       px-2.5 py-1.5 transition-colors disabled:opacity-50"
          >
            {dismissMutation.isPending
              ? <RefreshCw className="h-3 w-3 animate-spin" />
              : <X className="h-3 w-3" />}
          </button>
        </div>
      )}

      {isDone && (
        <p className="text-[10px] text-muted-foreground capitalize">{suggestion.status}</p>
      )}
    </div>
  );
}
