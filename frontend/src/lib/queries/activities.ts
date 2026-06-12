import { apiRequest } from "./_client";

// ── Public types ──────────────────────────────────────────────────────────────

export type ActivityType =
  | "note"
  | "task"
  | "call"
  | "meeting"
  | "email"
  | "system";

export interface ActivityRow {
  id: string;
  leadId: string;
  activityType: ActivityType;
  title: string | null;
  body: string | null;
  metadata: Record<string, unknown> | null;
  dueDate: string | null;
  completedAt: string | null;
  createdBy: string | null;
  createdByName: string | null;
  createdAt: string;
}

export interface ActivityCreate {
  activityType: ActivityType;
  title?: string | null;
  body?: string | null;
  metadata?: Record<string, unknown> | null;
  dueDate?: string | null;
  completedAt?: string | null;
}

export interface ActivityUpdate {
  title?: string | null;
  body?: string | null;
  dueDate?: string | null;
  completedAt?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface ActivityFilters {
  page?: number;
}

// ── Internal raw backend shapes ───────────────────────────────────────────────

interface _RawActivity {
  id: string;
  lead_id: string;
  activity_type: string;
  title: string | null;
  body: string | null;
  extra_data: Record<string, unknown> | null;
  due_date: string | null;
  completed_at: string | null;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
}

interface _RawActivityListResponse {
  items: _RawActivity[];
  total: number;
  page: number;
  page_size: number;
}

// ── Mapping helpers ───────────────────────────────────────────────────────────

function _mapActivity(raw: _RawActivity): ActivityRow {
  return {
    id: raw.id,
    leadId: raw.lead_id,
    activityType: raw.activity_type as ActivityType,
    title: raw.title,
    body: raw.body,
    metadata: raw.extra_data,
    dueDate: raw.due_date,
    completedAt: raw.completed_at,
    createdBy: raw.created_by,
    createdByName: raw.created_by_name,
    createdAt: raw.created_at,
  };
}

// ── Query functions ───────────────────────────────────────────────────────────

export async function getActivities(
  leadId: string,
  filters: ActivityFilters = {}
): Promise<{ items: ActivityRow[]; total: number; page: number; pageSize: number }> {
  const qs = new URLSearchParams();
  if (filters.page != null) qs.set("page", String(filters.page));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  const raw = await apiRequest<_RawActivityListResponse>(
    `/api/v1/contacts/${leadId}/activities${query}`
  );
  return {
    items: raw.items.map(_mapActivity),
    total: raw.total,
    page: raw.page,
    pageSize: raw.page_size,
  };
}

export async function createActivity(
  leadId: string,
  data: ActivityCreate
): Promise<ActivityRow> {
  const body = {
    activity_type: data.activityType,
    title: data.title ?? null,
    body: data.body ?? null,
    extra_data: data.metadata ?? null,
    due_date: data.dueDate ?? null,
    completed_at: data.completedAt ?? null,
  };
  const raw = await apiRequest<_RawActivity>(
    `/api/v1/contacts/${leadId}/activities`,
    { method: "POST", body: JSON.stringify(body) }
  );
  return _mapActivity(raw);
}

export async function updateActivity(
  leadId: string,
  activityId: string,
  data: ActivityUpdate
): Promise<ActivityRow> {
  const body: Record<string, unknown> = {};
  if ("title" in data) body.title = data.title;
  if ("body" in data) body.body = data.body;
  if ("dueDate" in data) body.due_date = data.dueDate;
  if ("completedAt" in data) body.completed_at = data.completedAt;
  if ("metadata" in data) body.extra_data = data.metadata;
  const raw = await apiRequest<_RawActivity>(
    `/api/v1/contacts/${leadId}/activities/${activityId}`,
    { method: "PATCH", body: JSON.stringify(body) }
  );
  return _mapActivity(raw);
}
