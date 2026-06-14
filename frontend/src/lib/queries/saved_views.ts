import { apiRequest } from "./_client";
import type { ContactFilters } from "./contacts";

export interface SavedViewRow {
  id: string;
  userId: string;
  tenantId: string;
  name: string;
  filters: ContactFilters;
  viewMode: "list" | "kanban" | "cards";
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
}

interface _RawSavedView {
  id: string;
  user_id: string;
  tenant_id: string;
  name: string;
  filters: Record<string, unknown>;
  view_mode: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

function _map(raw: _RawSavedView): SavedViewRow {
  return {
    id: raw.id,
    userId: raw.user_id,
    tenantId: raw.tenant_id,
    name: raw.name,
    filters: raw.filters as ContactFilters,
    viewMode: raw.view_mode as SavedViewRow["viewMode"],
    isDefault: raw.is_default,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

export async function getSavedViews(): Promise<SavedViewRow[]> {
  const raw = await apiRequest<_RawSavedView[]>("/api/v1/contacts/views");
  return raw.map(_map);
}

export async function createSavedView(data: {
  name: string;
  filters: ContactFilters;
  viewMode: SavedViewRow["viewMode"];
  isDefault: boolean;
}): Promise<SavedViewRow> {
  const raw = await apiRequest<_RawSavedView>("/api/v1/contacts/views", {
    method: "POST",
    body: JSON.stringify({
      name: data.name,
      filters: data.filters,
      view_mode: data.viewMode,
      is_default: data.isDefault,
    }),
  });
  return _map(raw);
}

export async function updateSavedView(
  id: string,
  data: Partial<{
    name: string;
    filters: ContactFilters;
    viewMode: SavedViewRow["viewMode"];
    isDefault: boolean;
  }>
): Promise<SavedViewRow> {
  const body: Record<string, unknown> = {};
  if ("name" in data) body.name = data.name;
  if ("filters" in data) body.filters = data.filters;
  if ("viewMode" in data) body.view_mode = data.viewMode;
  if ("isDefault" in data) body.is_default = data.isDefault;
  const raw = await apiRequest<_RawSavedView>(`/api/v1/contacts/views/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return _map(raw);
}

export async function deleteSavedView(id: string): Promise<void> {
  return apiRequest<void>(`/api/v1/contacts/views/${id}`, { method: "DELETE" });
}

export async function setDefaultView(id: string): Promise<SavedViewRow> {
  const raw = await apiRequest<_RawSavedView>(
    `/api/v1/contacts/views/${id}/set-default`,
    { method: "POST" }
  );
  return _map(raw);
}
