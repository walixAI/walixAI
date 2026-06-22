/**
 * Pipeline module — types, queries y mutations (MVP Sprint 14B).
 *
 * Portado de Supabase → FastAPI (apiRequest). Mapea snake_case→camelCase y title↔name.
 * Endpoints (Sprint 14A):
 *   GET   /api/pipeline/stages
 *   GET   /api/pipeline/deals
 *   POST  /api/deals
 *   PATCH /api/deals/{id}
 *
 * BOUNDARY Lead/Deal: el deal referencia a la persona por lead_id (expuesto como contactId).
 * contact_last_activity_at es una FECHA derivada del lead — no se copia más info del lead al deal.
 *
 * FASE 2 (omitido a propósito): multi-pipeline, tasks, unread, stage history, deal drawer,
 * sugerencias IA, aiMemory. Ver notas al pie.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";
import { resolveOwner, useTenantUsers } from "@/lib/queries/tenantUsers";

// ── Tipos ───────────────────────────────────────────────────────────────────────
export interface PipelineStage {
  id: string;
  name: string;
  position: number;        // mapeado desde order_index
  color: string;
  isWon: boolean;
  isLost: boolean;
  defaultProbability: number; // 14C.1 — probabilidad por etapa
  pipelineId: string | null;
}

export interface PipelineDeal {
  id: string;
  name: string;            // ← title del backend
  amount: number;
  probability: number;
  stageId: string | null;  // ← pipeline_stage_id
  stageName: string;
  contactId: string | null; // ← lead_id (la persona)
  contactLastActivityAt: string | null; // ← fecha derivada del lead
  ownerId: string | null;
  ownerName: string;
  ownerInitials: string;
  ownerColor: string;
  expectedCloseDate: string | null;
  source: string;
  notes: string | null;
  isWon: boolean;
  isLost: boolean;
  lostReason: string | null;
  lostComment: string | null;
  createdAt: string;
  updatedAt: string;
}

function mapDeal(r: any, users?: any[]): PipelineDeal {
  const owner = resolveOwner(users, r.owner_id ?? null); // owner_id puede no existir → "Sin asignar"
  return {
    id: r.id,
    name: r.title ?? r.name ?? "—",       // title↔name
    amount: Number(r.amount ?? 0),
    probability: r.probability ?? 0,
    stageId: r.pipeline_stage_id ?? r.stage_id ?? null,
    stageName: r.stage_name ?? "—",
    contactId: r.lead_id ?? null,
    contactLastActivityAt: r.contact_last_activity_at ?? null,
    ownerId: r.owner_id ?? null,
    ownerName: owner.name,
    ownerInitials: owner.initials,
    ownerColor: owner.color,
    expectedCloseDate: r.expected_close_date ?? null,
    source: r.source ?? "Manual",
    notes: r.notes ?? null,
    isWon: !!r.is_won,
    isLost: !!r.is_lost,
    lostReason: r.lost_reason ?? null,
    lostComment: r.lost_comment ?? null,
    createdAt: r.created_at,
    updatedAt: r.updated_at,
  };
}

// ── Etapas ──────────────────────────────────────────────────────────────────────
export function useStages() {
  return useQuery({
    queryKey: ["pipeline-stages"],
    queryFn: async (): Promise<PipelineStage[]> => {
      const rows = await apiRequest<any[]>("/api/pipeline/stages");
      return (rows ?? []).map((s) => ({
        id: s.id,
        name: s.name,
        position: s.order_index ?? s.position ?? 0,
        color: s.color ?? "#6B7280",
        isWon: !!s.is_won,
        isLost: !!s.is_lost,
        defaultProbability: s.default_probability ?? 0, // el endpoint mapea probability_default → default_probability
        pipelineId: null, // FASE 2: multi-pipeline
      }));
    },
  });
}

// ── Deals ───────────────────────────────────────────────────────────────────────
export function useDeals() {
  const { data: users } = useTenantUsers();
  return useQuery({
    // Clave EXACTA ["pipeline-deals"] para que el optimistic update funcione.
    queryKey: ["pipeline-deals"],
    queryFn: async (): Promise<PipelineDeal[]> => {
      const rows = await apiRequest<any[]>("/api/pipeline/deals");
      return (rows ?? []).map((r) => mapDeal(r, users));
    },
  });
}

// ── Drag & drop: cambiar de etapa ─────────────────────────────────────────────────
export function useUpdateDealStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: { dealId: string; stage: PipelineStage }) => {
      await apiRequest(`/api/deals/${args.dealId}`, {
        method: "PATCH",
        body: JSON.stringify({
          pipeline_stage_id: args.stage.id,
          is_won: args.stage.isWon,
          is_lost: args.stage.isLost,
        }),
      });
      // El backend (14A) registra deal_stage_history automáticamente al cambiar de etapa.
    },
    onMutate: async ({ dealId, stage }) => {
      await qc.cancelQueries({ queryKey: ["pipeline-deals"] });
      const prev = qc.getQueryData<PipelineDeal[]>(["pipeline-deals"]);
      if (prev) {
        qc.setQueryData<PipelineDeal[]>(
          ["pipeline-deals"],
          prev.map((d) =>
            d.id === dealId
              ? {
                  ...d,
                  stageId: stage.id,
                  stageName: stage.name,
                  isWon: stage.isWon,
                  isLost: stage.isLost,
                  // Espejo del backend (14C.1): al no enviar probability explícita,
                  // el deal hereda la probabilidad por defecto de la etapa destino.
                  probability: stage.defaultProbability,
                  updatedAt: new Date().toISOString(),
                }
              : d,
          ),
        );
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["pipeline-deals"], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["pipeline-deals"] }),
  });
}

// ── Patch genérico (usado por "Cerrado Perdido") ───────────────────────────────────
export function useUpdateDeal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: { dealId: string; patch: Record<string, any> }) => {
      await apiRequest(`/api/deals/${args.dealId}`, {
        method: "PATCH",
        body: JSON.stringify(args.patch),
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline-deals"] }),
  });
}

// ── Crear deal ─────────────────────────────────────────────────────────────────────
export interface NewDealInput {
  name: string;
  amount: number;
  probability: number;
  stageId: string;
  contactId: string;            // lead_id — OBLIGATORIO (FK NOT NULL en el modelo Deal)
  expectedCloseDate: string | null;
  source: string;
  notes: string | null;
}

export function useCreateDeal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: NewDealInput) => {
      return apiRequest<{ id: string }>("/api/deals", {
        method: "POST",
        body: JSON.stringify({
          title: input.name,                    // name→title
          lead_id: input.contactId,             // contactId→lead_id
          pipeline_stage_id: input.stageId,     // stageId→pipeline_stage_id
          amount: input.amount,
          probability: input.probability,
          expected_close_date: input.expectedCloseDate,
          source: input.source,
          notes: input.notes,
          // is_won/is_lost los maneja el backend (default False). FASE 2: heredar de la etapa.
        }),
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline-deals"] }),
  });
}

// ── Contactos (leads) — best-effort para resolver nombre/color en la tarjeta ─────────
// AJUSTA el endpoint/campos si tu módulo de leads difiere. Degrada con gracia a [].
export interface ContactLite {
  id: string;
  name: string;
  lastName: string | null;
  avatarColor: string | null;
}
export function useContactsLite() {
  return useQuery({
    queryKey: ["pipeline-contacts-lite"],
    queryFn: async (): Promise<ContactLite[]> => {
      try {
        const rows = await apiRequest<any[]>("/api/leads?limit=500");
        const arr = Array.isArray(rows) ? rows : (rows as any)?.items ?? [];
        return arr.map((c: any) => ({
          id: c.id,
          name: c.name ?? c.first_name ?? "—",
          lastName: c.last_name ?? null,
          avatarColor: c.avatar_color ?? null,
        }));
      } catch {
        return []; // TODO: alinear con el endpoint real de leads
      }
    },
  });
}

// ── Historial de etapas (14C.3-back) ──────────────────────────────────────────────
export interface StageHistoryRow {
  id: string;
  fromStageId: string | null;
  toStageId: string | null;
  fromStageName: string | null;
  toStageName: string | null;
  changedAt: string;
}

export function useStageHistory(dealId: string | undefined) {
  return useQuery({
    queryKey: ["deal-stage-history", dealId],
    enabled: !!dealId,
    queryFn: async (): Promise<StageHistoryRow[]> => {
      const rows = await apiRequest<any[]>(`/api/deals/${dealId}/stage-history`);
      return (rows ?? []).map((r) => ({
        id: r.id,
        fromStageId: r.from_stage_id ?? null,
        toStageId: r.to_stage_id ?? null,
        fromStageName: r.from_stage_name ?? null,
        toStageName: r.to_stage_name ?? null,
        changedAt: r.changed_at,
      }));
    },
  });
}

// ── Helpers ─────────────────────────────────────────────────────────────────────
export function formatMXN(n: number): string {
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 0,
  }).format(n);
}

export function daysSince(iso: string): number {
  const ms = Date.now() - new Date(iso).getTime();
  return Math.max(0, Math.floor(ms / 86400000));
}

/* ───────────────────────────────────────────────────────────────────────────────
   FASE 2 (no portado): usePipelines/useCreatePipeline/useRenamePipeline/useDeletePipeline,
   useDaysInCurrentStage, useDeal, useUpdateDealAmount,
   useDealTasksMap, useUnreadByContactMap, useDealActivity, useDealAiSuggestions, aiMemory.
   ─────────────────────────────────────────────────────────────────────────────── */
