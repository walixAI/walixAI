/**
 * Finance module — tipos, queries y mutations (Sprint 11/12).
 *
 * Cubre: permisos de finanzas, categorías de gasto, gastos, gastos recurrentes,
 * reglas de gasto. Todos los endpoints viven bajo /api/finance/.
 *
 * Portado de Supabase → FastAPI (apiRequest). Mapea snake_case→camelCase.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";

// ── Tipos: Permisos ───────────────────────────────────────────────────────────

export interface FinancePermission {
  id: string;
  tenantId: string;
  branchId: string | null;
  userId: string;
  grantedBy: string | null;
  userName: string;
  userEmail: string;
}

function mapPermission(r: any): FinancePermission {
  return {
    id: r.id,
    tenantId: r.tenant_id,
    branchId: r.branch_id ?? null,
    userId: r.user_id,
    grantedBy: r.granted_by ?? null,
    userName: r.user_name ?? "—",
    userEmail: r.user_email ?? "",
  };
}

// ── Tipos: Categorías de gasto ────────────────────────────────────────────────

export interface ExpenseCategory {
  id: string;
  tenantId: string;
  name: string;
  kind: "fijo" | "variable";
  icon: string | null;
  isActive: boolean;
}

function mapExpenseCategory(r: any): ExpenseCategory {
  return {
    id: r.id,
    tenantId: r.tenant_id,
    name: r.name,
    kind: r.kind,
    icon: r.icon ?? null,
    isActive: !!r.is_active,
  };
}

// ── Tipos: Gastos ─────────────────────────────────────────────────────────────

export interface Expense {
  id: string;
  tenantId: string;
  branchId: string | null;
  categoryId: string | null;
  ownerId: string | null;
  amount: number;
  kind: "fijo" | "variable";
  currency: string;
  incurredAt: string;
  status: "draft" | "confirmed";
  source: string;
  dealId: string | null;
  ruleId: string | null;
  recurringId: string | null;
  receiptUrl: string | null;
  description: string | null;
}

function mapExpense(r: any): Expense {
  return {
    id: r.id,
    tenantId: r.tenant_id,
    branchId: r.branch_id ?? null,
    categoryId: r.category_id ?? null,
    ownerId: r.owner_id ?? null,
    amount: Number(r.amount ?? 0),
    kind: r.kind,
    currency: r.currency ?? "MXN",
    incurredAt: r.incurred_at,
    status: r.status,
    source: r.source ?? "manual",
    dealId: r.deal_id ?? null,
    ruleId: r.rule_id ?? null,
    recurringId: r.recurring_id ?? null,
    receiptUrl: r.receipt_url ?? null,
    description: r.description ?? null,
  };
}

export interface ExpenseFilters {
  month?: string;           // YYYY-MM-DD (primer día del mes)
  kind?: "fijo" | "variable";
  categoryId?: string;
  status?: "draft" | "confirmed";
  branchId?: string;
}

// ── Tipos: Gastos recurrentes ─────────────────────────────────────────────────

export interface RecurringExpense {
  id: string;
  tenantId: string;
  categoryId: string | null;
  amount: number;
  dayOfMonth: number;
  description: string | null;
  isActive: boolean;
}

function mapRecurringExpense(r: any): RecurringExpense {
  return {
    id: r.id,
    tenantId: r.tenant_id,
    categoryId: r.category_id ?? null,
    amount: Number(r.amount ?? 0),
    dayOfMonth: r.day_of_month,
    description: r.description ?? null,
    isActive: !!r.is_active,
  };
}

// ── Tipos: Reglas de gasto ────────────────────────────────────────────────────

export interface ExpenseRule {
  id: string;
  tenantId: string;
  categoryId: string | null;
  name: string;
  ruleType: "percent_of_deal" | "fixed_per_deal" | "percent_of_cost";
  value: number;
  dealTypeFilter: string | null;
  autoConfirm: boolean;
  isActive: boolean;
}

function mapExpenseRule(r: any): ExpenseRule {
  return {
    id: r.id,
    tenantId: r.tenant_id,
    categoryId: r.category_id ?? null,
    name: r.name,
    ruleType: r.rule_type,
    value: Number(r.value ?? 0),
    dealTypeFilter: r.deal_type_filter ?? null,
    autoConfirm: !!r.auto_confirm,
    isActive: !!r.is_active,
  };
}

// ── Permisos de finanzas ──────────────────────────────────────────────────────

export function useFinancePermissions() {
  return useQuery({
    queryKey: ["finance-permissions"],
    queryFn: async (): Promise<FinancePermission[]> => {
      const rows = await apiRequest<any[]>("/api/finance/permissions");
      return (rows ?? []).map(mapPermission);
    },
  });
}

export function useGrantFinancePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { userId: string; branchId?: string | null }) =>
      apiRequest<any>("/api/finance/permissions", {
        method: "POST",
        body: JSON.stringify({
          user_id: input.userId,
          branch_id: input.branchId ?? null,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["finance-permissions"] }),
  });
}

export function useRevokeFinancePermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (permissionId: string) =>
      apiRequest(`/api/finance/permissions/${permissionId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["finance-permissions"] }),
  });
}

// ── Categorías de gasto ───────────────────────────────────────────────────────

export function useExpenseCategories(includeInactive = false) {
  return useQuery({
    queryKey: ["expense-categories", includeInactive],
    queryFn: async (): Promise<ExpenseCategory[]> => {
      const qs = includeInactive ? "?include_inactive=true" : "";
      const rows = await apiRequest<any[]>(`/api/finance/expense-categories${qs}`);
      return (rows ?? []).map(mapExpenseCategory);
    },
  });
}

export function useCreateExpenseCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; kind: "fijo" | "variable"; icon?: string | null }) =>
      apiRequest<any>("/api/finance/expense-categories", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expense-categories"] }),
  });
}

export function useUpdateExpenseCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: string;
      patch: { name?: string; kind?: "fijo" | "variable"; icon?: string | null; isActive?: boolean };
    }) =>
      apiRequest<any>(`/api/finance/expense-categories/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: patch.name,
          kind: patch.kind,
          icon: patch.icon,
          is_active: patch.isActive,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expense-categories"] }),
  });
}

// ── Gastos ────────────────────────────────────────────────────────────────────

export function useExpenses(filters: ExpenseFilters = {}) {
  return useQuery({
    queryKey: ["expenses", filters],
    queryFn: async (): Promise<Expense[]> => {
      const params = new URLSearchParams();
      if (filters.month) params.set("month", filters.month);
      if (filters.kind) params.set("kind", filters.kind);
      if (filters.categoryId) params.set("category_id", filters.categoryId);
      if (filters.status) params.set("status", filters.status);
      if (filters.branchId) params.set("branch_id", filters.branchId);
      const qs = params.toString() ? `?${params.toString()}` : "";
      const rows = await apiRequest<any[]>(`/api/finance/expenses${qs}`);
      return (rows ?? []).map(mapExpense);
    },
  });
}

export function useCreateExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      amount: number;
      kind: "fijo" | "variable";
      incurredAt?: string | null;
      branchId?: string | null;
      categoryId?: string | null;
      currency?: string;
      dealId?: string | null;
      receiptUrl?: string | null;
      description?: string | null;
    }) =>
      apiRequest<any>("/api/finance/expenses", {
        method: "POST",
        body: JSON.stringify({
          amount: input.amount,
          kind: input.kind,
          incurred_at: input.incurredAt ?? null,
          branch_id: input.branchId ?? null,
          category_id: input.categoryId ?? null,
          currency: input.currency ?? "MXN",
          deal_id: input.dealId ?? null,
          receipt_url: input.receiptUrl ?? null,
          description: input.description ?? null,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses"] }),
  });
}

export function useUpdateExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: string;
      patch: {
        amount?: number;
        kind?: "fijo" | "variable";
        incurredAt?: string | null;
        branchId?: string | null;
        categoryId?: string | null;
        currency?: string;
        status?: "draft" | "confirmed";
        dealId?: string | null;
        receiptUrl?: string | null;
        description?: string | null;
      };
    }) =>
      apiRequest<any>(`/api/finance/expenses/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          amount: patch.amount,
          kind: patch.kind,
          incurred_at: patch.incurredAt,
          branch_id: patch.branchId,
          category_id: patch.categoryId,
          currency: patch.currency,
          status: patch.status,
          deal_id: patch.dealId,
          receipt_url: patch.receiptUrl,
          description: patch.description,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses"] }),
  });
}

export function useConfirmExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, amount }: { id: string; amount?: number | null }) =>
      apiRequest<any>(`/api/finance/expenses/${id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ amount: amount ?? null }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses"] }),
  });
}

export function useConfirmAllExpenses() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<{ updated: number }>("/api/finance/expenses/confirm-all", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses"] }),
  });
}

export function useDeleteExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/finance/expenses/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses"] }),
  });
}

// ── Gastos recurrentes ────────────────────────────────────────────────────────

export function useRecurringExpenses(includeInactive = false) {
  return useQuery({
    queryKey: ["recurring-expenses", includeInactive],
    queryFn: async (): Promise<RecurringExpense[]> => {
      const qs = includeInactive ? "?include_inactive=true" : "";
      const rows = await apiRequest<any[]>(`/api/finance/recurring-expenses${qs}`);
      return (rows ?? []).map(mapRecurringExpense);
    },
  });
}

export function useCreateRecurringExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      amount: number;
      dayOfMonth: number;
      categoryId?: string | null;
      description?: string | null;
    }) =>
      apiRequest<any>("/api/finance/recurring-expenses", {
        method: "POST",
        body: JSON.stringify({
          amount: input.amount,
          day_of_month: input.dayOfMonth,
          category_id: input.categoryId ?? null,
          description: input.description ?? null,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recurring-expenses"] }),
  });
}

export function useUpdateRecurringExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: string;
      patch: {
        amount?: number;
        dayOfMonth?: number;
        categoryId?: string | null;
        description?: string | null;
        isActive?: boolean;
      };
    }) =>
      apiRequest<any>(`/api/finance/recurring-expenses/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          amount: patch.amount,
          day_of_month: patch.dayOfMonth,
          category_id: patch.categoryId,
          description: patch.description,
          is_active: patch.isActive,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recurring-expenses"] }),
  });
}

export function useDeleteRecurringExpense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/finance/recurring-expenses/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recurring-expenses"] }),
  });
}

export function useGenerateRecurringExpenses() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<{ generated: number }>("/api/finance/recurring-expenses/generate", {
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses"] }),
  });
}

// ── Reglas de gasto ───────────────────────────────────────────────────────────

export function useExpenseRules(includeInactive = false) {
  return useQuery({
    queryKey: ["expense-rules", includeInactive],
    queryFn: async (): Promise<ExpenseRule[]> => {
      const qs = includeInactive ? "?include_inactive=true" : "";
      const rows = await apiRequest<any[]>(`/api/finance/expense-rules${qs}`);
      return (rows ?? []).map(mapExpenseRule);
    },
  });
}

export function useCreateExpenseRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      name: string;
      ruleType: "percent_of_deal" | "fixed_per_deal" | "percent_of_cost";
      value: number;
      categoryId?: string | null;
      dealTypeFilter?: string | null;
      autoConfirm?: boolean;
    }) =>
      apiRequest<any>("/api/finance/expense-rules", {
        method: "POST",
        body: JSON.stringify({
          name: input.name,
          rule_type: input.ruleType,
          value: input.value,
          category_id: input.categoryId ?? null,
          deal_type_filter: input.dealTypeFilter ?? null,
          auto_confirm: input.autoConfirm ?? false,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expense-rules"] }),
  });
}

export function useUpdateExpenseRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: string;
      patch: {
        name?: string;
        ruleType?: "percent_of_deal" | "fixed_per_deal" | "percent_of_cost";
        value?: number;
        categoryId?: string | null;
        dealTypeFilter?: string | null;
        autoConfirm?: boolean;
        isActive?: boolean;
      };
    }) =>
      apiRequest<any>(`/api/finance/expense-rules/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: patch.name,
          rule_type: patch.ruleType,
          value: patch.value,
          category_id: patch.categoryId,
          deal_type_filter: patch.dealTypeFilter,
          auto_confirm: patch.autoConfirm,
          is_active: patch.isActive,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expense-rules"] }),
  });
}

export function useDeleteExpenseRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/finance/expense-rules/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expense-rules"] }),
  });
}

// ── Desglose mensual de gastos confirmados (client-side) ──────────────────────

export interface ExpenseBreakdown {
  fijo: number;
  variable: number;
  total: number;
  bySeller: { userId: string; amount: number }[];
}

export function useMonthExpenseBreakdown(enabled = true) {
  const today = new Date();
  const month = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;

  return useQuery({
    queryKey: ["expense-breakdown-month", month],
    enabled,
    queryFn: async (): Promise<ExpenseBreakdown> => {
      const qs = new URLSearchParams({ status: "confirmed", month });
      const rows = await apiRequest<any[]>(`/api/finance/expenses?${qs.toString()}`);
      const expenses = (rows ?? []).map(mapExpense);

      const fijo = expenses
        .filter((e) => e.kind === "fijo")
        .reduce((s, e) => s + e.amount, 0);
      const variable = expenses
        .filter((e) => e.kind === "variable")
        .reduce((s, e) => s + e.amount, 0);

      const bySellerMap: Record<string, number> = {};
      expenses.forEach((e) => {
        if (e.ownerId) {
          bySellerMap[e.ownerId] = (bySellerMap[e.ownerId] ?? 0) + e.amount;
        }
      });

      return {
        fijo,
        variable,
        total: fijo + variable,
        bySeller: Object.entries(bySellerMap)
          .map(([userId, amount]) => ({ userId, amount }))
          .sort((a, b) => b.amount - a.amount),
      };
    },
  });
}
