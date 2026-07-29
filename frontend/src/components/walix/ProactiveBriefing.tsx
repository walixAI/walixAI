import { toast } from "sonner";
import {
  Sparkles, MessageCircle, BarChart3, Settings2, Target, RefreshCw, UserPlus, X, Check,
} from "lucide-react";
import {
  useAgentSuggestions, useConfirmSuggestion, useDismissSuggestion, isConfirmable,
  type AiSuggestion, type AgentType,
} from "@/lib/queries/agentSuggestions";
import { relativeTime } from "@/lib/format/relativeTime";
import { cn } from "@/lib/utils";

// Estética por tipo de agente (icono + acento de color). Reemplaza el "priority" de Lovable,
// que no existe en agent_suggestions.
function agentMeta(t: AgentType): { Icon: typeof Sparkles; color: string; accent: string } {
  switch (t) {
    case "follow_up":
      return { Icon: MessageCircle, color: "text-success", accent: "border-l-success" };
    case "closing":
      return { Icon: Target, color: "text-primary", accent: "border-l-primary" };
    case "pipeline":
      return { Icon: BarChart3, color: "text-warning", accent: "border-l-warning" };
    case "config":
      return { Icon: Settings2, color: "text-info", accent: "border-l-info" };
    case "reactivation":
      return { Icon: RefreshCw, color: "text-accent", accent: "border-l-accent" };
    case "profile_enrichment":
      return { Icon: UserPlus, color: "text-muted-foreground", accent: "border-l-border" };
    default:
      return { Icon: Sparkles, color: "text-muted-foreground", accent: "border-l-border" };
  }
}

export function ProactiveBriefing() {
  const { data: suggestions = [], isLoading } = useAgentSuggestions();
  const confirm = useConfirmSuggestion();
  const dismiss = useDismissSuggestion();
  const top = suggestions.slice(0, 5);
  const lastUpdate = top[0]?.createdAt;

  const handleConfirm = (s: AiSuggestion) => {
    confirm.mutate(s.id, {
      onSuccess: () => toast.success("Sugerencia confirmada — ejecutándose"),
      onError: () => toast.error("No se pudo confirmar"),
    });
  };
  const handleDismiss = (s: AiSuggestion) => {
    dismiss.mutate({ id: s.id }, {
      onSuccess: () => toast.success("Sugerencia descartada"),
      onError: () => toast.error("No se pudo descartar"),
    });
  };

  return (
    <div
      id="proactive-briefing"
      className="rounded-xl border border-border border-l-4 border-l-primary bg-primary/5 dark:bg-primary/10 p-5 shadow-card flex flex-col"
    >
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-semibold flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary" />
          Tu briefing de hoy
        </h3>
        {lastUpdate && (
          <span className="text-[10px] text-muted-foreground">
            Actualizado {relativeTime(lastUpdate)}
          </span>
        )}
      </div>
      <p className="text-[10px] text-muted-foreground mb-4">
        {suggestions.length} sugerencia{suggestions.length === 1 ? "" : "s"} activa{suggestions.length === 1 ? "" : "s"}
      </p>

      <div className="space-y-2">
        {top.map((s) => {
          const meta = agentMeta(s.agentType);
          const confirmable = isConfirmable(s);
          return (
            <div
              key={s.id}
              className={cn(
                "rounded-lg bg-card border border-border border-l-4 p-3 hover:border-primary/40 transition-colors relative",
                meta.accent,
              )}
            >
              <button
                onClick={() => handleDismiss(s)}
                disabled={dismiss.isPending}
                className="absolute top-2 right-2 text-muted-foreground hover:text-foreground"
                aria-label="Descartar"
              >
                <X className="h-3.5 w-3.5" />
              </button>

              <div className="flex items-start gap-2 mb-1 pr-5">
                <meta.Icon className={cn("h-4 w-4 shrink-0 mt-0.5", meta.color)} />
                <p className="text-sm leading-snug text-foreground line-clamp-2 flex-1">
                  {s.suggestionText}
                </p>
              </div>
              {s.triggerDescription && (
                <p className="text-[11px] text-muted-foreground mb-2 pl-6 line-clamp-1">
                  {s.triggerDescription}
                </p>
              )}

              <div className="flex items-center justify-end gap-2">
                <button
                  onClick={() => handleDismiss(s)}
                  disabled={dismiss.isPending}
                  className="text-[11px] text-muted-foreground hover:text-foreground"
                >
                  Descartar
                </button>
                {confirmable ? (
                  <button
                    onClick={() => handleConfirm(s)}
                    disabled={confirm.isPending}
                    className="text-xs font-semibold text-primary-foreground bg-primary hover:bg-primary/90 rounded-md px-2.5 py-1 inline-flex items-center gap-1 disabled:opacity-50"
                  >
                    <Check className="h-3 w-3" /> Confirmar
                  </button>
                ) : (
                  // reactivation / profile_enrichment: ejecución no implementada en backend.
                  <span className="text-[10px] text-muted-foreground italic">Solo informativa</span>
                )}
              </div>
            </div>
          );
        })}

        {top.length === 0 && (
          <div className="text-xs text-muted-foreground italic">
            {isLoading ? "Cargando sugerencias…" : "Sin sugerencias activas. La IA está observando…"}
          </div>
        )}
      </div>
    </div>
  );
}

/* Diferencias vs. el original de Lovable:
   - Datos: agent_suggestions reales (no la tabla ai_proactive_suggestions de Supabase).
   - Acciones: Confirmar (ejecuta vía Celery) + Descartar, en vez del botón action_type.
   - reactivation/profile_enrichment NO muestran "Confirmar" (executor no implementado).
   - Sin priority/barra, sin "Gemini 2.5 Flash", sin navegación a entidad (el lead_id
     vive dentro de action_payload; navegación = mejora posterior). */
