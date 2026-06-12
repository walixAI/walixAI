/**
 * Shared fetch wrapper for the queries/ layer.
 * Mirrors the logic of src/lib/api.ts → request() but is exported so each
 * query module can use it without touching the monolithic api.ts.
 */
import { clearToken, getToken } from "../api";

export const BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const { body } = init;

  // Don't set Content-Type for FormData — browser must set boundary automatically
  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  if (res.status === 401) {
    clearToken();
    window.location.replace("/login");
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const d = (await res.json()) as { detail?: unknown };
      detail = typeof d.detail === "string" ? d.detail : undefined;
    } catch {
      // ignore JSON parse failure
    }
    throw new Error(detail ?? `HTTP ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
