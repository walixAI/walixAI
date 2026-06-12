import { apiRequest } from "./_client";

// ── Public types ──────────────────────────────────────────────────────────────

export type { TagRow } from "./contacts";

// ── Internal raw backend shapes ───────────────────────────────────────────────

interface _RawTag {
  id: string;
  name: string;
  color: string | null;
}

// ── Query functions ───────────────────────────────────────────────────────────

export async function getTags(): Promise<{ id: string; name: string; color: string | null }[]> {
  const raw = await apiRequest<_RawTag[]>("/api/v1/tags");
  return raw.map((t) => ({ id: t.id, name: t.name, color: t.color }));
}

export async function createTag(
  name: string,
  color?: string | null
): Promise<{ id: string; name: string; color: string | null }> {
  const body: Record<string, unknown> = { name };
  if (color !== undefined) body.color = color;
  const raw = await apiRequest<_RawTag>("/api/v1/tags", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return { id: raw.id, name: raw.name, color: raw.color };
}
