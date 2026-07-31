/**
 * Goals module — tipos, queries y mutations (Sprint 11/12).
 *
 * Cubre: categorías de producto, metas mensuales (upsert vía POST), assignments.
 * Todos los endpoints viven bajo /api/goals/.
 *
 * Semántica de upsert: POST /monthly-goals crea o actualiza la meta con la misma
 * (periodo, dimension, dimension_value_*). PATCH /{id} edita campos sueltos.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";

// ── Tipos: Categorías de producto ─────────────────────────────────────────────

export interface ProductCategory {
  id: string;
  tenantId: string;
  name: string;
  isActive: boolean;
  position: number;
}

function mapProductCategory(r: any): ProductCategory {
  return {
    id: r.id,
    tenantId: r.tenant_id,
    name: r.name,
    isActive: !!r.is_active,
    position: r.position ?? 0,
  };
}

// ── Tipos: Metas mensuales ────────────────────────────────────────────────────

export type GoalDimension = "global" | "deal_type" | "pipeline" | "product_category";

export interface MonthlyGoal {
  id: string;
  tenantId: string;
  periodYear: number;
  periodMonth: number;
  amount: number;
  currency: string;
  dimension: GoalDimension;
  dimensionValueText: string | null;
  dimensionValueUuid: string | null;
  notes: string | null;
  isDraft: boolean;
  createdBy: string | null;
}

function mapMonthlyGoal(r: any): MonthlyGoal {
  return {
    id: r.id,
    tenantId: r.tenant_id,
    periodYear: r.period_year,
    periodMonth: r.period_month,
    amount: Number(r.amount ?? 0),
    currency: r.currency ?? "MXN",
    dimension: r.dimension,
    dimensionValueText: r.dimension_value_text ?? null,
    dimensionValueUuid: r.dimension_value_uuid ?? null,
    notes: r.notes ?? null,
    isDraft: !!r.is_draft,
    createdBy: r.created_by ?? null,
  };
}

export interface MonthlyGoalFilters {
  periodYear?: number;
  periodMonth?: number;
  dimension?: GoalDimension;
  includeDraft?: boolean;
}

// ── Tipos: Assignments ────────────────────────────────────────────────────────

export interface GoalAssignment {
  id: string;
  goalId: string;
  tenantId: string;
  userId: string;
  sharePercent: number;
  amount: number;
  userName: string;
  userEmail: string;
}

function mapGoalAssignment(r: any): GoalAssignment {
  return {
    id: r.id,
    goalId: r.goal_id,
    tenantId: r.tenant_id,
    userId: r.user_id,
    sharePercent: Number(r.share_percent ?? 0),
    amount: Number(r.amount ?? 0),
    userName: r.user_name ?? "—",
    userEmail: r.user_email ?? "",
  };
}

// ── Categorías de producto ────────────────────────────────────────────────────

export function useProductCategories(includeInactive = false) {
  return useQuery({
    queryKey: ["product-categories", includeInactive],
    queryFn: async (): Promise<ProductCategory[]> => {
      const qs = includeInactive ? "?include_inactive=true" : "";
      const rows = await apiRequest<any[]>(`/api/goals/product-categories${qs}`);
      return (rows ?? []).map(mapProductCategory);
    },
  });
}

export function useCreateProductCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; position?: number }) =>
      apiRequest<any>("/api/goals/product-categories", {
        method: "POST",
        body: JSON.stringify({ name: input.name, position: input.position ?? 0 }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["product-categories"] }),
  });
}

export function useUpdateProductCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: string;
      patch: { name?: string; isActive?: boolean; position?: number };
    }) =>
      apiRequest<any>(`/api/goals/product-categories/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: patch.name,
          is_active: patch.isActive,
          position: patch.position,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["product-categories"] }),
  });
}

// ── Metas mensuales ───────────────────────────────────────────────────────────

export function useMonthlyGoals(filters: MonthlyGoalFilters = {}) {
  return useQuery({
    queryKey: ["monthly-goals", filters],
    queryFn: async (): Promise<MonthlyGoal[]> => {
      const params = new URLSearchParams();
      if (filters.periodYear != null) params.set("period_year", String(filters.periodYear));
      if (filters.periodMonth != null) params.set("period_month", String(filters.periodMonth));
      if (filters.dimension) params.set("dimension", filters.dimension);
      if (filters.includeDraft != null) params.set("include_draft", String(filters.includeDraft));
      const qs = params.toString() ? `?${params.toString()}` : "";
      const rows = await apiRequest<any[]>(`/api/goals/monthly-goals${qs}`);
      return (rows ?? []).map(mapMonthlyGoal);
    },
  });
}

// Upsert: POST crea o actualiza la meta con la misma (periodo, dimension, value).
export function useSaveMonthlyGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      periodYear: number;
      periodMonth: number;
      amount: number;
      dimension: GoalDimension;
      dimensionValueText?: string | null;
      dimensionValueUuid?: string | null;
      currency?: string;
      notes?: string | null;
      isDraft?: boolean;
    }) =>
      apiRequest<any>("/api/goals/monthly-goals", {
        method: "POST",
        body: JSON.stringify({
          period_year: input.periodYear,
          period_month: input.periodMonth,
          amount: input.amount,
          dimension: input.dimension,
          dimension_value_text: input.dimensionValueText ?? null,
          dimension_value_uuid: input.dimensionValueUuid ?? null,
          currency: input.currency ?? "MXN",
          notes: input.notes ?? null,
          is_draft: input.isDraft ?? false,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["monthly-goals"] }),
  });
}

export function useUpdateMonthlyGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: string;
      patch: {
        amount?: number;
        currency?: string;
        notes?: string | null;
        isDraft?: boolean;
      };
    }) =>
      apiRequest<any>(`/api/goals/monthly-goals/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          amount: patch.amount,
          currency: patch.currency,
          notes: patch.notes,
          is_draft: patch.isDraft,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["monthly-goals"] }),
  });
}

// ── Assignments ───────────────────────────────────────────────────────────────

export function useGoalAssignments(goalId: string | undefined) {
  return useQuery({
    queryKey: ["goal-assignments", goalId],
    enabled: !!goalId,
    queryFn: async (): Promise<GoalAssignment[]> => {
      const rows = await apiRequest<any[]>(`/api/goals/monthly-goals/${goalId}/assignments`);
      return (rows ?? []).map(mapGoalAssignment);
    },
  });
}

export function useSetGoalAssignments(goalId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assignments: Array<{ userId: string; sharePercent: number }>) =>
      apiRequest<any[]>(`/api/goals/monthly-goals/${goalId}/assignments`, {
        method: "PUT",
        body: JSON.stringify({
          assignments: assignments.map((a) => ({
            user_id: a.userId,
            share_percent: a.sharePercent,
          })),
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["goal-assignments", goalId] });
      qc.invalidateQueries({ queryKey: ["monthly-goals"] });
    },
  });
}
