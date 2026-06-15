/**
 * Contacts module — types, filters, and API query functions.
 *
 * Backend returns snake_case JSON; this module exposes camelCase TypeScript
 * interfaces and maps the response before returning to callers.
 *
 * Status note: the backend Lead model uses "nuevo" | "en_calificacion" |
 * "calificado" | "escalado" | "perdido".  LeadStatus below uses those same
 * values so filters round-trip correctly.
 */
import { getToken } from "../api";
import { apiRequest, BASE_URL } from "./_client";

// ── Public types ──────────────────────────────────────────────────────────────

export type LeadStatus =
  | "nuevo"
  | "en_calificacion"
  | "calificado"
  | "escalado"
  | "perdido";

export type ProspectionSource = string; // "manual" | "whatsapp_inbound" | etc.

export interface TagRow {
  id: string;
  name: string;
  color: string | null;
}

export interface UserMinimal {
  id: string;
  name: string;
  /** Not yet returned by the backend; reserved for future avatar support. */
  avatarUrl: string | null;
}

export interface ContactRow {
  id: string;
  /** May be absent if tenant_id is not included in the list response. */
  tenantId?: string;
  name: string | null;
  lastName: string | null;
  /** wa_phone from the backend */
  phone: string | null;
  /** No email field on the Lead model yet; always null until backend adds it. */
  email: string | null;
  company: string | null;
  status: LeadStatus;
  prospectionSource: ProspectionSource;
  tags: TagRow[];
  assignedUser: UserMinimal | null;
  currentScore: number | null;
  /** Backend returns "up" | "down" | "flat"; "flat" is normalised to "stable". */
  currentScoreTrend: "up" | "down" | "stable" | null;
  lastActivitySummary: string | null;
  /** Proxy: maps from updated_at until a dedicated last_activity_at column exists. */
  lastActivityAt: string | null;
  createdAt: string;
  deletedAt: string | null;
}

export interface ContactFilters {
  q?: string;
  status?: LeadStatus[];
  source?: ProspectionSource[];
  tag?: string[];
  assigned?: string[];
  dateFrom?: string;
  dateTo?: string;
  sort?: "name" | "company" | "status" | "lastActivity";
  order?: "asc" | "desc";
  page?: number;
}

export interface ContactListResponse {
  items: ContactRow[];
  total: number;
  page: number;
  pageSize: number;
}

// ── Internal raw backend shapes ───────────────────────────────────────────────

interface _RawTag {
  id: string;
  name: string;
  color: string | null;
}

interface _RawUser {
  id: string;
  name: string;
  email: string;
}

interface _RawContact {
  id: string;
  tenant_id?: string;
  wa_phone: string | null;
  name: string | null;
  last_name: string | null;
  company: string | null;
  status: string;
  prospection_source: string;
  deleted_at: string | null;
  last_activity_summary: string | null;
  pipeline_stage_id: string | null;
  current_score: number | null;
  current_score_trend: string | null;
  created_at: string;
  updated_at: string;
  tags: _RawTag[];
  assigned_user: _RawUser | null;
}

interface _RawListResponse {
  items: _RawContact[];
  total: number;
  page: number;
  page_size: number;
}

// ── Mapping helpers ───────────────────────────────────────────────────────────

function _mapTrend(raw: string | null): ContactRow["currentScoreTrend"] {
  if (raw === "up") return "up";
  if (raw === "down") return "down";
  if (raw === "flat" || raw === "stable") return "stable";
  return null;
}

function _mapContact(raw: _RawContact): ContactRow {
  return {
    id: raw.id,
    tenantId: raw.tenant_id,
    name: raw.name,
    lastName: raw.last_name,
    phone: raw.wa_phone,
    email: null,
    company: raw.company,
    status: raw.status as LeadStatus,
    prospectionSource: raw.prospection_source,
    tags: (raw.tags ?? []).map((t) => ({ id: t.id, name: t.name, color: t.color })),
    assignedUser: raw.assigned_user
      ? { id: raw.assigned_user.id, name: raw.assigned_user.name, avatarUrl: null }
      : null,
    currentScore: raw.current_score,
    currentScoreTrend: _mapTrend(raw.current_score_trend),
    lastActivitySummary: raw.last_activity_summary,
    lastActivityAt: raw.updated_at ?? null,
    createdAt: raw.created_at,
    deletedAt: raw.deleted_at,
  };
}

// ── Filter → query string ─────────────────────────────────────────────────────

function _filtersToQs(f: ContactFilters): string {
  const qs = new URLSearchParams();
  if (f.q) qs.set("q", f.q);
  f.status?.forEach((s) => qs.append("status", s));
  f.source?.forEach((s) => qs.append("source", s));
  f.tag?.forEach((t) => qs.append("tag", t));
  f.assigned?.forEach((a) => qs.append("assigned", a));
  if (f.dateFrom) qs.set("date_from", f.dateFrom);
  if (f.dateTo) qs.set("date_to", f.dateTo);
  if (f.sort) qs.set("sort", f.sort);
  if (f.order) qs.set("order", f.order);
  if (f.page != null) qs.set("page", String(f.page));
  const s = qs.toString();
  return s ? `?${s}` : "";
}

// ── Query functions ───────────────────────────────────────────────────────────

export async function getContacts(
  filters: ContactFilters = {}
): Promise<ContactListResponse> {
  const raw = await apiRequest<_RawListResponse>(
    `/api/v1/contacts${_filtersToQs(filters)}`
  );
  return {
    items: raw.items.map(_mapContact),
    total: raw.total,
    page: raw.page,
    pageSize: raw.page_size,
  };
}

export async function getContact(id: string): Promise<ContactRow> {
  const raw = await apiRequest<_RawContact>(`/api/v1/contacts/${id}`);
  return _mapContact(raw);
}

export async function createContact(data: Partial<ContactRow>): Promise<ContactRow> {
  // Reverse-map camelCase fields back to snake_case for the POST body
  const body = {
    wa_phone: data.phone || null,
    name: data.name ?? null,
    last_name: data.lastName ?? null,
    company: data.company ?? null,
    prospection_source: data.prospectionSource ?? "manual",
    pipeline_stage_id: null as string | null,
    tag_ids: [] as string[],
  };
  const raw = await apiRequest<_RawContact>("/api/v1/contacts", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return _mapContact(raw);
}

export async function updateContact(
  id: string,
  data: Partial<ContactRow>
): Promise<ContactRow> {
  const body: Record<string, unknown> = {};
  if ("name" in data) body.name = data.name;
  if ("lastName" in data) body.last_name = data.lastName;
  if ("company" in data) body.company = data.company;
  if ("prospectionSource" in data) body.prospection_source = data.prospectionSource;
  if ("status" in data) body.status = data.status;
  if ("tags" in data) body.tag_ids = (data.tags ?? []).map((t) => t.id);
  if ("assignedUser" in data) body.assigned_user_id = data.assignedUser?.id ?? null;
  const raw = await apiRequest<_RawContact>(`/api/v1/contacts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return _mapContact(raw);
}

export async function deleteContact(id: string): Promise<void> {
  return apiRequest<void>(`/api/v1/contacts/${id}`, { method: "DELETE" });
}

export async function bulkContacts(
  action: "reassign" | "status" | "tag" | "delete",
  ids: string[],
  payload: Record<string, unknown> = {}
): Promise<{ updated: number }> {
  return apiRequest<{ updated: number }>("/api/v1/contacts/bulk", {
    method: "POST",
    body: JSON.stringify({ action, ids, payload }),
  });
}

/**
 * Triggers a CSV download using the same auth token.
 * Fetches as a blob (so the Bearer header is included) then creates a
 * temporary anchor click — required because native browser download
 * doesn't support Authorization headers.
 */
export async function exportContactsCsv(filters: ContactFilters = {}): Promise<void> {
  const token = getToken();
  const url = `${BASE_URL}/api/v1/contacts/export${_filtersToQs(filters)}`;

  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!res.ok) {
    throw new Error(`Export falló: HTTP ${res.status}`);
  }

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const today = new Date().toISOString().split("T")[0];
  anchor.href = objectUrl;
  anchor.download = `walix-contactos-${today}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
}

export async function importContacts(
  file: File
): Promise<{ jobId: string; totalRows: number }> {
  const form = new FormData();
  form.append("file", file);
  const raw = await apiRequest<{ job_id: string; total_rows: number }>(
    "/api/v1/contacts/import",
    { method: "POST", body: form }
  );
  return { jobId: raw.job_id, totalRows: raw.total_rows };
}

export async function getImportJob(jobId: string): Promise<{
  status: string;
  processed: number;
  total: number;
  errors: unknown[];
  errorCsvBase64?: string;
}> {
  const raw = await apiRequest<{
    status: string;
    processed: number;
    total: number;
    errors: unknown[];
    error_csv_base64?: string;
  }>(`/api/v1/contacts/import/${jobId}`);
  return {
    status: raw.status,
    processed: raw.processed,
    total: raw.total,
    errors: raw.errors,
    ...(raw.error_csv_base64 ? { errorCsvBase64: raw.error_csv_base64 } : {}),
  };
}
