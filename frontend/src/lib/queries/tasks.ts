import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";
import { updateActivity, type ClosedVia } from "./activities";

// ── TaskRow (general list) ─────────────────────────────────────────────────────

export interface TaskRow {
  id: string;
  title: string | null;
  taskKind: string | null;
  dueDate: string | null;
  overdue: boolean;
  completedAt: string | null;
  leadId: string;
  leadName: string | null;
  dealId: string | null;
  dealTitle: string | null;
  dealAmount: number | null;
  assigneeId: string | null;
  assigneeName: string | null;
}

export type TaskView = "today" | "upcoming" | "overdue" | "completed" | "all";

interface _RawGeneralItem {
  id: string;
  title: string | null;
  task_kind: string | null;
  due_date: string | null;
  overdue: boolean;
  completed_at: string | null;
  lead_id: string;
  lead_name: string | null;
  deal_id: string | null;
  deal_title: string | null;
  deal_amount: number | null;
  assignee_id: string | null;
  assignee_name: string | null;
}

function _mapGeneral(r: _RawGeneralItem): TaskRow {
  return {
    id: r.id,
    title: r.title,
    taskKind: r.task_kind,
    dueDate: r.due_date,
    overdue: r.overdue,
    completedAt: r.completed_at,
    leadId: r.lead_id,
    leadName: r.lead_name,
    dealId: r.deal_id,
    dealTitle: r.deal_title,
    dealAmount: r.deal_amount,
    assigneeId: r.assignee_id,
    assigneeName: r.assignee_name,
  };
}

// ── Types ──────────────────────────────────────────────────────────────────────

export interface TaskTodayItem {
  id: string;
  title: string | null;
  taskKind: string | null;
  dueDate: string | null;
  overdue: boolean;
  leadId: string;
  leadName: string | null;
  dealId: string | null;
  dealTitle: string | null;
  dealAmount: number | null;
}

export interface TaskTodayTotals {
  total: number;
  overdue: number;
  byKind: Record<string, number>;
  collectAmount: number;
}

export interface TaskTodayResponse {
  items: TaskTodayItem[];
  totals: TaskTodayTotals;
}

// ── Raw backend shape ──────────────────────────────────────────────────────────

interface _RawTaskItem {
  id: string;
  title: string | null;
  task_kind: string | null;
  due_date: string | null;
  overdue: boolean;
  lead_id: string;
  lead_name: string | null;
  deal_id: string | null;
  deal_title: string | null;
  deal_amount: number | null;
}

interface _RawTotals {
  total: number;
  overdue: number;
  by_kind: Record<string, number>;
  collect_amount: number;
}

interface _RawResponse {
  items: _RawTaskItem[];
  totals: _RawTotals;
}

function _mapItem(r: _RawTaskItem): TaskTodayItem {
  return {
    id: r.id,
    title: r.title,
    taskKind: r.task_kind,
    dueDate: r.due_date,
    overdue: r.overdue,
    leadId: r.lead_id,
    leadName: r.lead_name,
    dealId: r.deal_id,
    dealTitle: r.deal_title,
    dealAmount: r.deal_amount,
  };
}

// ── Hooks ──────────────────────────────────────────────────────────────────────

export function useMyTasksToday() {
  return useQuery({
    queryKey: ["tasks-today"],
    staleTime: 60_000,
    queryFn: async (): Promise<TaskTodayResponse> => {
      const raw = await apiRequest<_RawResponse>("/api/tasks/today");
      return {
        items: raw.items.map(_mapItem),
        totals: {
          total: raw.totals.total,
          overdue: raw.totals.overdue,
          byKind: raw.totals.by_kind,
          collectAmount: raw.totals.collect_amount,
        },
      };
    },
  });
}

export function useTasks(params: {
  view: TaskView;
  mineOnly: boolean;
  contactId?: string | null;
}) {
  return useQuery({
    queryKey: ["tasks", params.view, params.mineOnly, params.contactId ?? null],
    staleTime: 30_000,
    queryFn: async (): Promise<TaskRow[]> => {
      const qs = new URLSearchParams({
        view: params.view,
        mine_only: String(params.mineOnly),
      });
      if (params.contactId) qs.set("lead_id", params.contactId);
      const raw = await apiRequest<_RawGeneralItem[]>(`/api/tasks?${qs}`);
      return raw.map(_mapGeneral);
    },
  });
}

export function useDeleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) =>
      apiRequest<void>(`/api/tasks/${taskId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["tasks-today"] });
    },
  });
}

export function useCloseTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: {
      leadId: string;
      activityId: string;
      closedVia: ClosedVia;
      closedNote?: string | null;
      contactId?: string;
    }) => {
      return updateActivity(args.leadId, args.activityId, {
        completedAt: new Date().toISOString(),
        closedVia: args.closedVia,
        closedNote: args.closedNote ?? null,
      });
    },
    onSuccess: (_data, args) => {
      qc.invalidateQueries({ queryKey: ["tasks-today"] });
      if (args.contactId) {
        qc.invalidateQueries({ queryKey: ["activities", args.contactId] });
      }
    },
  });
}
