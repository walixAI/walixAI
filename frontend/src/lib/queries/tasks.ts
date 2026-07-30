import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";
import { updateActivity, type ClosedVia } from "./activities";

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
