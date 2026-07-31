/**
 * Profitability & run-rate — queries de analytics (Sprint 11/12).
 *
 * Cubre: run-rate del tenant, rentabilidad del tenant, run-rate por usuario,
 * rentabilidad por usuario y sugerencia de reparto de meta.
 * Todos los endpoints viven bajo /api/finance/.
 *
 * goal-split-suggestion envía user_ids como params repetidos:
 *   ?user_ids=uuid1&user_ids=uuid2  (FastAPI list[uuid.UUID])
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";

// ── Tipos: Run-rate del tenant ────────────────────────────────────────────────

export interface TenantRunRate {
  year: number;
  month: number;
  wonRevenue: number;
  runRate: number;
  elapsedDays: number;
  totalDays: number;
  goalAmount: number | null;
  pctOfGoal: number | null;
  expectedToday: number;
  gap: number;
  status: "green" | "yellow" | "red";
  openQuotesAmount: number;
  openQuotesCount: number;
  negotiationAmount: number;
  negotiationCount: number;
  soldByDealType: Record<string, number>;
  recommendations: string[];
}

function mapTenantRunRate(r: any): TenantRunRate {
  return {
    year: r.year,
    month: r.month,
    wonRevenue: Number(r.won_revenue ?? 0),
    runRate: Number(r.run_rate ?? 0),
    elapsedDays: r.elapsed_days,
    totalDays: r.total_days,
    goalAmount: r.goal_amount != null ? Number(r.goal_amount) : null,
    pctOfGoal: r.pct_of_goal != null ? Number(r.pct_of_goal) : null,
    expectedToday: Number(r.expected_today ?? 0),
    gap: Number(r.gap ?? 0),
    status: r.status ?? "red",
    openQuotesAmount: Number(r.open_quotes_amount ?? 0),
    openQuotesCount: r.open_quotes_count ?? 0,
    negotiationAmount: Number(r.negotiation_amount ?? 0),
    negotiationCount: r.negotiation_count ?? 0,
    soldByDealType: r.sold_by_deal_type ?? {},
    recommendations: r.recommendations ?? [],
  };
}

// ── Tipos: Rentabilidad del tenant ────────────────────────────────────────────

export interface TenantProfitability {
  year: number;
  month: number;
  revenue: number;
  expenses: number;
  profit: number;
  profitPct: number | null;
  label: "green" | "yellow" | "orange" | "red" | "unknown";
}

function mapTenantProfitability(r: any): TenantProfitability {
  return {
    year: r.year,
    month: r.month,
    revenue: Number(r.revenue ?? 0),
    expenses: Number(r.expenses ?? 0),
    profit: Number(r.profit ?? 0),
    profitPct: r.profit_pct != null ? Number(r.profit_pct) : null,
    label: r.label ?? "unknown",
  };
}

// ── Tipos: Run-rate por usuario ───────────────────────────────────────────────

export interface UserRunRate {
  userId: string;
  year: number;
  month: number;
  wonRevenue: number;
  runRate: number;
  elapsedDays: number;
  totalDays: number;
  userGoal: number | null;
  pctOfGoal: number | null;
}

function mapUserRunRate(r: any): UserRunRate {
  return {
    userId: r.user_id,
    year: r.year,
    month: r.month,
    wonRevenue: Number(r.won_revenue ?? 0),
    runRate: Number(r.run_rate ?? 0),
    elapsedDays: r.elapsed_days,
    totalDays: r.total_days,
    userGoal: r.user_goal != null ? Number(r.user_goal) : null,
    pctOfGoal: r.pct_of_goal != null ? Number(r.pct_of_goal) : null,
  };
}

// ── Tipos: Rentabilidad por usuario ──────────────────────────────────────────

export interface UserProfitability {
  userId: string;
  year: number;
  month: number;
  revenue: number;
  expenses: number;
  profit: number;
  profitPct: number | null;
  label: "green" | "yellow" | "orange" | "red" | "unknown";
}

function mapUserProfitability(r: any): UserProfitability {
  return {
    userId: r.user_id,
    year: r.year,
    month: r.month,
    revenue: Number(r.revenue ?? 0),
    expenses: Number(r.expenses ?? 0),
    profit: Number(r.profit ?? 0),
    profitPct: r.profit_pct != null ? Number(r.profit_pct) : null,
    label: r.label ?? "unknown",
  };
}

// ── Run-rate del tenant ───────────────────────────────────────────────────────

export function useTenantRunRate(year?: number, month?: number) {
  return useQuery({
    queryKey: ["tenant-run-rate", year ?? null, month ?? null],
    queryFn: async (): Promise<TenantRunRate> => {
      const params = new URLSearchParams();
      if (year != null) params.set("year", String(year));
      if (month != null) params.set("month", String(month));
      const qs = params.toString() ? `?${params.toString()}` : "";
      const r = await apiRequest<any>(`/api/finance/run-rate${qs}`);
      return mapTenantRunRate(r);
    },
  });
}

// ── Rentabilidad del tenant ───────────────────────────────────────────────────

export function useTenantProfitability(year?: number, month?: number) {
  return useQuery({
    queryKey: ["tenant-profitability", year ?? null, month ?? null],
    queryFn: async (): Promise<TenantProfitability> => {
      const params = new URLSearchParams();
      if (year != null) params.set("year", String(year));
      if (month != null) params.set("month", String(month));
      const qs = params.toString() ? `?${params.toString()}` : "";
      const r = await apiRequest<any>(`/api/finance/profitability${qs}`);
      return mapTenantProfitability(r);
    },
  });
}

// ── Run-rate por usuario ──────────────────────────────────────────────────────

export function useUserRunRate(userId: string | undefined, year?: number, month?: number) {
  return useQuery({
    queryKey: ["user-run-rate", userId ?? null, year ?? null, month ?? null],
    enabled: !!userId,
    queryFn: async (): Promise<UserRunRate> => {
      const params = new URLSearchParams();
      if (year != null) params.set("year", String(year));
      if (month != null) params.set("month", String(month));
      const qs = params.toString() ? `?${params.toString()}` : "";
      const r = await apiRequest<any>(`/api/finance/run-rate/users/${userId}${qs}`);
      return mapUserRunRate(r);
    },
  });
}

// ── Rentabilidad por usuario ──────────────────────────────────────────────────

export function useUserProfitability(userId: string | undefined, year?: number, month?: number) {
  return useQuery({
    queryKey: ["user-profitability", userId ?? null, year ?? null, month ?? null],
    enabled: !!userId,
    queryFn: async (): Promise<UserProfitability> => {
      const params = new URLSearchParams();
      if (year != null) params.set("year", String(year));
      if (month != null) params.set("month", String(month));
      const qs = params.toString() ? `?${params.toString()}` : "";
      const r = await apiRequest<any>(`/api/finance/profitability/users/${userId}${qs}`);
      return mapUserProfitability(r);
    },
  });
}

// ── Sugerencia de reparto de meta ─────────────────────────────────────────────

export type GoalSplitDimension = "global" | "deal_type" | "pipeline" | "product_category";

export interface GoalSplitParams {
  dimension: GoalSplitDimension;
  dimensionValueText?: string | null;
  dimensionValueUuid?: string | null;
  userIds: string[];
}

export function useGoalSplitSuggestion(params: GoalSplitParams | null) {
  return useQuery({
    queryKey: ["goal-split-suggestion", params],
    enabled: params !== null && params.userIds.length > 0,
    queryFn: async (): Promise<Record<string, number>> => {
      // FastAPI list[uuid.UUID] requires repeated params: ?user_ids=a&user_ids=b
      const qs = new URLSearchParams();
      qs.set("dimension", params!.dimension);
      if (params!.dimensionValueText) qs.set("dimension_value_text", params!.dimensionValueText);
      if (params!.dimensionValueUuid) qs.set("dimension_value_uuid", params!.dimensionValueUuid);
      for (const uid of params!.userIds) {
        qs.append("user_ids", uid);
      }
      const r = await apiRequest<Record<string, number>>(
        `/api/finance/goal-split-suggestion?${qs.toString()}`,
      );
      return r ?? {};
    },
  });
}

// ── Run-rate por vendedor (solo owner/platform_owner pueden ver otros) ────────

export interface SellerRunRate {
  userId: string;
  name: string;
  wonRevenue: number;
  runRate: number;
  userGoal: number | null;
  pctOfGoal: number | null;
}

export function useRunRateBySeller(enabled = true, year?: number, month?: number) {
  return useQuery({
    queryKey: ["run-rate-by-seller", enabled, year ?? null, month ?? null],
    enabled,
    queryFn: async (): Promise<SellerRunRate[]> => {
      const users = await apiRequest<any[]>("/api/users");
      const active = (users ?? []).filter(
        (u) => u.is_active && u.role !== "platform_owner",
      );
      const params = new URLSearchParams();
      if (year != null) params.set("year", String(year));
      if (month != null) params.set("month", String(month));
      const qs = params.toString() ? `?${params.toString()}` : "";

      const results = await Promise.all(
        active.map(async (u) => {
          try {
            const r = await apiRequest<any>(`/api/finance/run-rate/users/${u.id}${qs}`);
            return { u, r };
          } catch {
            return null;
          }
        }),
      );

      return results
        .filter(Boolean)
        .map((item) => ({
          userId: item!.u.id as string,
          name: (item!.u.full_name ?? item!.u.name ?? item!.u.email ?? "—") as string,
          wonRevenue: Number(item!.r.won_revenue ?? 0),
          runRate: Number(item!.r.run_rate ?? 0),
          userGoal: item!.r.user_goal != null ? Number(item!.r.user_goal) : null,
          pctOfGoal: item!.r.pct_of_goal != null ? Number(item!.r.pct_of_goal) : null,
        }))
        .sort((a, b) => b.wonRevenue - a.wonRevenue);
    },
  });
}

// ── Finance settings ──────────────────────────────────────────────────────────

export interface FinanceSettings {
  countBusinessDays: boolean;
  profitThresholds: { green: number; yellow: number; orange: number };
}

function mapFinanceSettings(r: any): FinanceSettings {
  const t = r.profit_thresholds ?? {};
  return {
    countBusinessDays: !!r.count_business_days,
    profitThresholds: {
      green: Number(t.green ?? 20),
      yellow: Number(t.yellow ?? 10),
      orange: Number(t.orange ?? 0),
    },
  };
}

export function useFinanceSettings() {
  return useQuery({
    queryKey: ["finance-settings"],
    queryFn: async (): Promise<FinanceSettings> => {
      const r = await apiRequest<any>("/api/finance/settings");
      return mapFinanceSettings(r);
    },
  });
}

export function useUpdateFinanceSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<FinanceSettings>) =>
      apiRequest<any>("/api/finance/settings", {
        method: "PATCH",
        body: JSON.stringify({
          ...(input.countBusinessDays !== undefined && {
            count_business_days: input.countBusinessDays,
          }),
          ...(input.profitThresholds && {
            profit_thresholds: {
              green: input.profitThresholds.green,
              yellow: input.profitThresholds.yellow,
              orange: input.profitThresholds.orange,
            },
          }),
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["finance-settings"] }),
  });
}
