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

// ── Pipelines ───────────────────────────────────────────────────────────────────
export interface PipelineItem {
  id: string;
  name: string;
  isDefault: boolean;
  position: number;
  branchId: string;
}

export function usePipelines() {
  return useQuery({
    queryKey: ["pipelines"],
    queryFn: async (): Promise<PipelineItem[]> => {
      const rows = await apiRequest<any[]>("/api/pipelines");
      return (rows ?? []).map((p) => ({
        id: p.id,
        name: p.name,
        isDefault: !!p.is_default,
        position: p.position ?? 0,
        branchId: p.branch_id,
      }));
    },
  });
}

export function useCreatePipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; branch_id: string }) =>
      apiRequest<{ id: string; name: string; is_default: boolean; position: number; branch_id: string }>(
        "/api/pipelines",
        { method: "POST", body: JSON.stringify(input) },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelines"] }),
  });
}

export function useRenamePipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      apiRequest(`/api/pipelines/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelines"] }),
  });
}

export function useDeletePipeline() {
  const qc = useQueryClient();
  return useMutation({
    // apiRequest propaga e.message con el detail exacto del 409 del backend
    mutationFn: (id: string) =>
      apiRequest(`/api/pipelines/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelines"] }),
  });
}

// ── Etapas ──────────────────────────────────────────────────────────────────────
export function useStages(pipelineId?: string | null) {
  return useQuery({
    queryKey: ["pipeline-stages", pipelineId ?? null],
    queryFn: async (): Promise<PipelineStage[]> => {
      const qs = pipelineId ? `?pipeline_id=${pipelineId}` : "";
      const rows = await apiRequest<any[]>(`/api/pipeline/stages${qs}`);
      return (rows ?? []).map((s) => ({
        id: s.id,
        name: s.name,
        position: s.order_index ?? s.position ?? 0,
        color: s.color ?? "#6B7280",
        isWon: !!s.is_won,
        isLost: !!s.is_lost,
        defaultProbability: s.default_probability ?? 0,
        pipelineId: s.pipeline_id ?? null,
      }));
    },
  });
}

// ── Deals ───────────────────────────────────────────────────────────────────────
export function useDeals(pipelineId?: string | null) {
  const { data: users } = useTenantUsers();
  return useQuery({
    queryKey: ["pipeline-deals", pipelineId ?? null],
    queryFn: async (): Promise<PipelineDeal[]> => {
      const qs = pipelineId ? `?pipeline_id=${pipelineId}` : "";
      const rows = await apiRequest<any[]>(`/api/pipeline/deals${qs}`);
      return (rows ?? []).map((r) => mapDeal(r, users));
    },
  });
}

// ── Drag & drop: cambiar de etapa ─────────────────────────────────────────────────
// pipelineId se pasa para que el optimistic update pueda localizar la cache exacta.
export function useUpdateDealStage(pipelineId?: string | null) {
  const qc = useQueryClient();
  const dealKey = ["pipeline-deals", pipelineId ?? null] as const;
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
    },
    onMutate: async ({ dealId, stage }) => {
      // Cancela cualquier variante activa de pipeline-deals (prefix match)
      await qc.cancelQueries({ queryKey: ["pipeline-deals"] });
      const prev = qc.getQueryData<PipelineDeal[]>(dealKey);
      if (prev) {
        qc.setQueryData<PipelineDeal[]>(
          dealKey,
          prev.map((d) =>
            d.id === dealId
              ? {
                  ...d,
                  stageId: stage.id,
                  stageName: stage.name,
                  isWon: stage.isWon,
                  isLost: stage.isLost,
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
      if (ctx?.prev) qc.setQueryData(dealKey, ctx.prev);
    },
    // exact: false (default en v5) invalida todas las variantes ["pipeline-deals", *]
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
    // Invalida todas las variantes de pipeline-deals (prefix match)
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
    // Invalida todas las variantes de pipeline-deals (prefix match)
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
