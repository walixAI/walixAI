/**
 * Agent suggestions (IA proactiva) — Dashboard fase 2.
 *
 * Conecta a /api/agents/suggestions (shape real del backend, array plano).
 *   GET    /api/agents/suggestions            → AiSuggestion[]  (ya filtra por rol/usuario)
 *   POST   /api/agents/suggestions/{id}/confirm  (sin body)     → AiSuggestion (202)
 *   POST   /api/agents/suggestions/{id}/dismiss  { reason? }     → AiSuggestion (200)
 *
 * Mapea snake_case→camelCase como el resto de la capa de queries.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";

export type AgentType =
  | "follow_up" | "pipeline" | "closing" | "config" | "reactivation" | "profile_enrichment";

export type SuggestionStatus =
  | "suggested" | "accepted" | "confirmed" | "executed" | "dismissed" | "expired" | "failed";

export interface AiSuggestion {
  id: string;
  agentType: AgentType;
  triggerDescription: string;
  suggestionText: string;
  actionPayload: Record<string, unknown> | null;
  targetRole: "asesor" | "gerente" | "owner";
  targetUserId: string | null;
  status: SuggestionStatus;
  executionResult: Record<string, unknown> | null;
  errorDetail: string | null;
  respondedAt: string | null;
  expiresAt: string;
  createdAt: string;
  updatedAt: string;
}

function mapSuggestion(r: any): AiSuggestion {
  return {
    id: r.id,
    agentType: r.agent_type,
    triggerDescription: r.trigger_description,
    suggestionText: r.suggestion_text,
    actionPayload: r.action_payload ?? null,
    targetRole: r.target_role,
    targetUserId: r.target_user_id ?? null,
    status: r.status,
    executionResult: r.execution_result ?? null,
    errorDetail: r.error_detail ?? null,
    respondedAt: r.responded_at ?? null,
    expiresAt: r.expires_at,
    createdAt: r.created_at,
    updatedAt: r.updated_at,
  };
}

/**
 * Tipos cuya ejecución NO está implementada en executor.py (_dispatch).
 * Confirmar una de estas deja la sugerencia en status="failed".
 * Hasta que el backend implemente _exec_reactivation / _exec_profile_enrichment,
 * la UI NO debe ofrecer el botón "Confirmar" para estos tipos.
 * TODO(backend fase 2): implementar estos ejecutores y quitar este bloqueo.
 */
const NON_EXECUTABLE_TYPES: ReadonlySet<AgentType> = new Set(["reactivation", "profile_enrichment"]);

export function isConfirmable(s: AiSuggestion): boolean {
  return !NON_EXECUTABLE_TYPES.has(s.agentType);
}

// ── Query ───────────────────────────────────────────────────────────────────────
export function useAgentSuggestions() {
  return useQuery({
    queryKey: ["agent-suggestions"],
    queryFn: async (): Promise<AiSuggestion[]> => {
      const rows = await apiRequest<any[]>("/api/agents/suggestions");
      return (rows ?? []).map(mapSuggestion);
    },
  });
}

// ── Confirmar (encola ejecución en Celery) ─────────────────────────────────────────
export function useConfirmSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<any>(`/api/agents/suggestions/${id}/confirm`, { method: "POST" }),
    // Optimista: la sugerencia confirmada sale de la lista (el GET solo trae status="suggested").
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["agent-suggestions"] });
      const prev = qc.getQueryData<AiSuggestion[]>(["agent-suggestions"]);
      if (prev) qc.setQueryData(["agent-suggestions"], prev.filter((s) => s.id !== id));
      return { prev };
    },
    onError: (_e, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(["agent-suggestions"], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["agent-suggestions"] }),
  });
}

// ── Descartar ──────────────────────────────────────────────────────────────────────
export function useDismissSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; reason?: string | null }) =>
      apiRequest<any>(`/api/agents/suggestions/${args.id}/dismiss`, {
        method: "POST",
        body: JSON.stringify({ reason: args.reason ?? null }),
      }),
    onMutate: async ({ id }) => {
      await qc.cancelQueries({ queryKey: ["agent-suggestions"] });
      const prev = qc.getQueryData<AiSuggestion[]>(["agent-suggestions"]);
      if (prev) qc.setQueryData(["agent-suggestions"], prev.filter((s) => s.id !== id));
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["agent-suggestions"], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["agent-suggestions"] }),
  });
}
