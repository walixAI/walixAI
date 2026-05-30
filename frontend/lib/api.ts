const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "walix_token";

export type UserRole = "owner" | "gerente" | "asesor" | "soporte" | "it";

export type LeadStatus =
  | "nuevo"
  | "en_calificacion"
  | "calificado"
  | "escalado"
  | "perdido";

export type LeadSentiment =
  | "neutral"
  | "interesado"
  | "urgente"
  | "negativo";

export type LeadSource = "whatsapp_inbound" | "meta_ads" | "manual";

export type ConversationStatus = "active" | "handoff" | "closed";
export type ConversationHandler = "bot" | "human";
export type MessageRole = "user" | "assistant" | "system";

export interface LoginUser {
  id: string;
  name: string;
  role: UserRole;
  branch_id: string | null;
  tenant_id: string;
}

export interface LoginResponse {
  access_token: string;
  user: LoginUser;
}

export interface UserMe extends LoginUser {
  email: string;
  is_active: boolean;
}

export interface LeadListItem {
  id: string;
  wa_phone: string;
  name: string | null;
  status: LeadStatus;
  sentiment: LeadSentiment;
  source: LeadSource;
  assigned_to: string | null;
  contact_phone: string | null;
  qualification_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface LeadListResponse {
  items: LeadListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface LeadDetail extends LeadListItem {
  branch_id: string;
  tenant_id: string;
  qualification_data: Record<string, unknown>;
  qualification_score: number | null;
  assigned_to_name: string | null;
}

export interface MessageOut {
  id: string;
  role: MessageRole;
  content: string;
  tokens_used: number | null;
  latency_ms: number | null;
  created_at: string;
}

export interface ConversationOut {
  conversation_id: string | null;
  status: ConversationStatus | null;
  handled_by: ConversationHandler | null;
  messages: MessageOut[];
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  if (res.status === 401) {
    // Token missing/expired — bounce to login. Skip the redirect when we're
    // already on /login so the form can show its own error.
    clearToken();
    if (
      typeof window !== "undefined" &&
      window.location.pathname !== "/login"
    ) {
      window.location.replace("/login");
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : undefined;
    } catch {
      // ignore non-JSON bodies
    }
    throw new Error(detail ?? `HTTP ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<UserMe>("/api/auth/me"),

  listLeads: (opts: {
    status?: LeadStatus;
    date?: string;
    all?: boolean;
    limit?: number;
    offset?: number;
  } = {}) => {
    const qs = new URLSearchParams();
    if (opts.status) qs.set("status", opts.status);
    if (opts.all) qs.set("all", "true");
    else if (opts.date) qs.set("date", opts.date);
    if (opts.limit !== undefined) qs.set("limit", String(opts.limit));
    if (opts.offset !== undefined) qs.set("offset", String(opts.offset));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<LeadListResponse>(`/api/leads${suffix}`);
  },

  getLead: (id: string) => request<LeadDetail>(`/api/leads/${id}`),

  getConversation: (id: string) =>
    request<ConversationOut>(`/api/leads/${id}/conversation`),

  updateLeadStatus: (
    id: string,
    body: { status: LeadStatus; note?: string | null },
  ) =>
    request<LeadDetail>(`/api/leads/${id}/status`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  handoff: (id: string) =>
    request<LeadDetail>(`/api/leads/${id}/handoff`, { method: "POST" }),

  returnToBot: (id: string) =>
    request<LeadDetail>(`/api/leads/${id}/return-to-bot`, { method: "POST" }),

  sendMessage: (id: string, text: string) =>
    request<MessageOut>(`/api/leads/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};
