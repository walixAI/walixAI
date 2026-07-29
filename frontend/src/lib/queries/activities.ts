import { apiRequest } from "./_client";

// ── Public types ──────────────────────────────────────────────────────────────

export type ActivityType =
  | "note"
  | "task"
  | "call"
  | "meeting"
  | "email"
  | "system";

export type TaskKind =
  | "cobro" | "cotizacion" | "servicio" | "seguimiento"
  | "queja" | "refaccion" | "facturacion" | "devolucion" | "otro";

export type ClosedVia = "whatsapp" | "email" | "call" | "manual" | "auto" | "other";

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
  // ── Etapa 5 task extensions ──
  taskKind?: TaskKind | null;
  assigneeId?: string | null;
  dealId?: string | null;
  closedVia?: ClosedVia | null;
  closedNote?: string | null;
}

export interface ActivityCreate {
  activityType: ActivityType;
  title?: string | null;
  body?: string | null;
  metadata?: Record<string, unknown> | null;
  dueDate?: string | null;
  completedAt?: string | null;
  // ── Etapa 5 task extensions ──
  taskKind?: TaskKind | null;
  assigneeId?: string | null;
  dealId?: string | null;
  closedVia?: ClosedVia | null;
  closedNote?: string | null;
}

export interface ActivityUpdate {
  title?: string | null;
  body?: string | null;
  dueDate?: string | null;
  completedAt?: string | null;
  metadata?: Record<string, unknown> | null;
  // ── Etapa 5 task extensions ──
  taskKind?: TaskKind | null;
  assigneeId?: string | null;
  dealId?: string | null;
  closedVia?: ClosedVia | null;
  closedNote?: string | null;
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
  // Etapa 5
  task_kind?: string | null;
  assignee_id?: string | null;
  deal_id?: string | null;
  closed_via?: string | null;
  closed_note?: string | null;
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
    taskKind: (raw.task_kind ?? null) as TaskKind | null,
    assigneeId: raw.assignee_id ?? null,
    dealId: raw.deal_id ?? null,
    closedVia: (raw.closed_via ?? null) as ClosedVia | null,
    closedNote: raw.closed_note ?? null,
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
  const body: Record<string, unknown> = {
    activity_type: data.activityType,
    title: data.title ?? null,
    body: data.body ?? null,
    extra_data: data.metadata ?? null,
    due_date: data.dueDate ?? null,
    completed_at: data.completedAt ?? null,
  };
  // Only include task extension fields when explicitly provided
  if ("taskKind" in data) body.task_kind = data.taskKind ?? null;
  if ("assigneeId" in data) body.assignee_id = data.assigneeId ?? null;
  if ("dealId" in data) body.deal_id = data.dealId ?? null;
  if ("closedVia" in data) body.closed_via = data.closedVia ?? null;
  if ("closedNote" in data) body.closed_note = data.closedNote ?? null;
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
  if ("taskKind" in data) body.task_kind = data.taskKind ?? null;
  if ("assigneeId" in data) body.assignee_id = data.assigneeId ?? null;
  if ("dealId" in data) body.deal_id = data.dealId ?? null;
  if ("closedVia" in data) body.closed_via = data.closedVia ?? null;
  if ("closedNote" in data) body.closed_note = data.closedNote ?? null;
  const raw = await apiRequest<_RawActivity>(
    `/api/v1/contacts/${leadId}/activities/${activityId}`,
    { method: "PATCH", body: JSON.stringify(body) }
  );
  return _mapActivity(raw);
}
