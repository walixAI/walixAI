// ── Walix API client ── connects to FastAPI backend ──────────────────────────

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const TOKEN_KEY = "walix_token";
const PLATFORM_TOKEN_BACKUP_KEY = "walix_platform_token_backup";
const IMPERSONATE_META_KEY = "walix_impersonate_meta";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string): void {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ── JWT utilities ─────────────────────────────────────────────────────────────

export function decodeJwtPayload(token: string): Record<string, unknown> {
  try {
    const b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(b64)) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export function isImpersonating(): boolean {
  const token = getToken();
  if (!token) return false;
  return Boolean(decodeJwtPayload(token).read_only_impersonation);
}

export function startImpersonation(impersonationToken: string, tenantName: string): void {
  const current = getToken();
  if (current) localStorage.setItem(PLATFORM_TOKEN_BACKUP_KEY, current);
  setToken(impersonationToken);
  localStorage.setItem(IMPERSONATE_META_KEY, tenantName);
}

export function endImpersonation(): void {
  const backup = localStorage.getItem(PLATFORM_TOKEN_BACKUP_KEY);
  if (backup) setToken(backup);
  localStorage.removeItem(PLATFORM_TOKEN_BACKUP_KEY);
  localStorage.removeItem(IMPERSONATE_META_KEY);
}

export function getImpersonatedTenantName(): string | null {
  return localStorage.getItem(IMPERSONATE_META_KEY);
}

// ── Types ─────────────────────────────────────────────────────────────────────

export type LeadStatus = "nuevo" | "en_calificacion" | "calificado" | "escalado" | "perdido";
export type Sentiment = "neutral" | "interesado" | "urgente" | "negativo";

export interface PipelineStageOut {
  id: string;
  name: string;
  slug: string;
  order_index: number;
  color: string | null;
  is_won: boolean;
  is_lost: boolean;
}

export interface LeadListItem {
  id: string;
  wa_phone: string;
  name: string | null;
  status: LeadStatus;
  sentiment: Sentiment;
  source: string;
  assigned_to: string | null;
  contact_phone: string | null;
  qualification_score: number | null;
  pipeline_stage_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadDetail extends LeadListItem {
  branch_id: string;
  tenant_id: string;
  qualification_data: Record<string, unknown>;
  assigned_to_name: string | null;
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tokens_used: number | null;
  latency_ms: number | null;
  created_at: string;
  sent_by_user_id: string | null;
}

export interface ReplyResponse {
  message_id: string;
  sent_at: string;
  status: string;
}

export interface ConversationOut {
  conversation_id: string | null;
  status: "active" | "handoff" | "closed" | null;
  current_handler: "bot" | "human" | null;
  handler_user_id: string | null;
  messages: MessageOut[];
}

export interface UserBrief {
  id: string;
  name: string;
  email: string;
  role: string;
}

export interface BranchOut {
  id: string;
  name: string;
}

export interface AgentOut {
  id: string;
  name: string;
  role: string;
  active_leads: number;
  wa_phone: string | null;
}

export interface MetaConfigOut {
  page_id: string;
  form_ids: string[];
  field_mapping: Record<string, string>;
  is_active: boolean;
  verify_token: string;
}

export interface MetaConfigIn {
  page_id: string;
  page_access_token: string;
  form_ids: string[];
  field_mapping: Record<string, string>;
}

export interface WalixUser {
  id: string;
  name: string;
  email: string;
  role: string;
  branch_id: string | null;
  tenant_id: string;
  is_active?: boolean;
}

export interface LeadListResponse {
  items: LeadListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface OnboardingDraftOut {
  id: string;
  branch_id: string;
  tenant_id: string;
  generated_config: Record<string, unknown>;
  business_input: string;
  status: string;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BranchOnboardingOut {
  id: string;
  name: string;
  ai_config: Record<string, unknown> | null;
  onboarding_status: string;
  bot_name: string | null;
  industry: string | null;
}

export interface TeamMemberOut {
  id: string;
  name: string;
  email: string;
  role: string;
  wa_phone: string | null;
  is_active: boolean;
  branch_id: string | null;
  created_at: string;
}

// ── HTTP core ─────────────────────────────────────────────────────────────────

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
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
      const d = await res.json();
      detail = typeof d.detail === "string" ? d.detail : undefined;
    } catch {
      // ignore parse error
    }
    throw new Error(detail ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Platform Owner types ──────────────────────────────────────────────────────

export interface RenewalItem {
  tenant_name: string;
  plan: string;
  renewal_date: string;
}

export interface PlatformStats {
  total_tenants: number;
  active_tenants: number;
  trials: number;
  churned_this_month: number;
  mrr_by_plan: Record<string, number>;
  total_mrr: number;
  renewals_next_30_days: RenewalItem[];
  ai_costs_this_month: number;
}

export interface PlatformTenantItem {
  id: string;
  name: string;
  plan: string;
  is_active: boolean;
  created_at: string;
  leads_count: number;
  ai_cost_this_month: number;
}

export interface ImpersonateResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  tenant_id: string;
}

// ── Pipeline board types ──────────────────────────────────────────────────────

export interface BoardLeadCard {
  id: string;
  name: string | null;
  wa_phone: string;
  status: LeadStatus;
  sentiment: Sentiment;
  risk_score: number | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  days_in_stage: number;
  qualification_score: number | null;
}

export interface PipelineStageBoardOut {
  id: string;
  name: string;
  slug: string;
  color: string | null;
  order_index: number;
  is_won: boolean;
  is_lost: boolean;
  leads: BoardLeadCard[];
  total: number;
}

export interface BoardResponse {
  stages: PipelineStageBoardOut[];
}

export interface LeadStageOut {
  id: string;
  pipeline_stage_id: string | null;
  stage_name: string | null;
  stage_slug: string | null;
}

// ── AI Bar types ──────────────────────────────────────────────────────────────

export interface AICommandRequest {
  message: string;
  context: Record<string, unknown>;
  history: Array<{ role: "user" | "assistant"; content: string }>;
}

export interface AICommandResponse {
  intent_type: string;
  response_text: string;
  requires_confirmation: boolean;
  actions_taken: Array<{ type: string; success: boolean; error?: string }>;
  suggested_actions: string[];
  tokens_used: number;
  latency_ms: number;
}

export interface ContextInsightResponse {
  insight: string;
  urgency: "low" | "medium" | "high";
  suggested_actions: string[];
}

// ── API object ────────────────────────────────────────────────────────────────

export const api = {
  // Auth
  async login(email: string, password: string): Promise<{ access_token: string; user: WalixUser }> {
    return request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  async me(): Promise<WalixUser> {
    return request("/api/auth/me");
  },

  // Leads
  async listLeads(params?: { all?: boolean; status?: LeadStatus; date?: string }): Promise<LeadListResponse> {
    const qs = new URLSearchParams();
    if (params?.all != null) qs.set("all", String(params.all));
    if (params?.status) qs.set("status", params.status);
    if (params?.date) qs.set("date", params.date);
    const q = qs.toString() ? `?${qs}` : "";
    return request(`/api/leads${q}`);
  },

  async getLead(id: string): Promise<LeadDetail> {
    return request(`/api/leads/${id}`);
  },

  async getConversation(leadId: string): Promise<ConversationOut> {
    return request(`/api/leads/${leadId}/conversation`);
  },

  async sendMessage(leadId: string, text: string): Promise<MessageOut> {
    return request(`/api/leads/${leadId}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },

  async reply(leadId: string, message: string): Promise<ReplyResponse> {
    return request(`/api/leads/${leadId}/reply`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
  },

  async handoff(leadId: string): Promise<LeadDetail> {
    return request(`/api/leads/${leadId}/handoff`, { method: "POST" });
  },

  async returnToBot(leadId: string): Promise<LeadDetail> {
    return request(`/api/leads/${leadId}/return-to-bot`, { method: "POST" });
  },

  async getAssignees(leadId: string): Promise<UserBrief[]> {
    return request(`/api/leads/${leadId}/assignees`);
  },

  async listBranches(): Promise<BranchOut[]> {
    return request("/api/branches");
  },

  async getBranchAgents(branchId: string): Promise<AgentOut[]> {
    return request(`/api/branches/${branchId}/agents`);
  },

  async getMetaConfig(branchId: string): Promise<MetaConfigOut | null> {
    return request(`/api/branches/${branchId}/meta-config`);
  },

  async saveMetaConfig(branchId: string, data: MetaConfigIn): Promise<MetaConfigOut> {
    return request(`/api/branches/${branchId}/meta-config`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async deleteMetaConfig(branchId: string): Promise<void> {
    return request(`/api/branches/${branchId}/meta-config`, { method: "DELETE" });
  },

  async assignLead(leadId: string, userId: string): Promise<LeadDetail> {
    return request(`/api/leads/${leadId}/assign`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  },

  async getBranchPipeline(branchId: string): Promise<PipelineStageOut[]> {
    return request(`/api/branches/${branchId}/pipeline`);
  },

  async generateOnboarding(data: {
    branch_id: string;
    business_description: string;
    industry: string;
  }): Promise<OnboardingDraftOut> {
    return request("/api/onboarding/generate", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async getDraft(draftId: string): Promise<OnboardingDraftOut> {
    return request(`/api/onboarding/drafts/${draftId}`);
  },

  async refineDraft(data: {
    draft_id: string;
    section: string;
    instruction: string;
  }): Promise<OnboardingDraftOut> {
    return request("/api/onboarding/refine", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async approveDraft(draftId: string): Promise<BranchOnboardingOut> {
    return request("/api/onboarding/approve", {
      method: "POST",
      body: JSON.stringify({ draft_id: draftId }),
    });
  },

  // Team
  async getTeam(branchId: string): Promise<TeamMemberOut[]> {
    return request(`/api/branches/${branchId}/team`);
  },

  async createTeamMember(
    branchId: string,
    data: { name: string; email: string; password: string; role: string; wa_phone?: string | null },
  ): Promise<TeamMemberOut> {
    return request(`/api/branches/${branchId}/team`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateUser(
    userId: string,
    data: { name?: string; wa_phone?: string | null; role?: string },
  ): Promise<TeamMemberOut> {
    return request(`/api/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async toggleUser(userId: string): Promise<TeamMemberOut> {
    return request(`/api/users/${userId}/toggle`, { method: "PATCH" });
  },

  // Platform Owner
  async getPlatformStats(): Promise<PlatformStats> {
    return request("/api/platform/stats");
  },

  async getPlatformTenants(): Promise<PlatformTenantItem[]> {
    return request("/api/platform/tenants");
  },

  async impersonateTenant(tenantId: string): Promise<ImpersonateResponse> {
    return request(`/api/platform/impersonate/${tenantId}`, { method: "POST" });
  },

  // Pipeline
  async getPipelineBoard(branchId?: string, limitPerStage = 50): Promise<BoardResponse> {
    const qs = new URLSearchParams({ limit_per_stage: String(limitPerStage) });
    if (branchId) qs.set("branch_id", branchId);
    return request(`/api/pipeline/board?${qs}`);
  },

  async moveLeadToStage(leadId: string, stageId: string): Promise<LeadStageOut> {
    return request(`/api/leads/${leadId}/stage`, {
      method: "PATCH",
      body: JSON.stringify({ stage_id: stageId, moved_by: "manual" }),
    });
  },

  // AI Bar
  async sendAICommand(data: AICommandRequest): Promise<AICommandResponse> {
    return request("/api/ai/command", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async getContextInsight(
    screen: string,
    branch_id?: string,
  ): Promise<ContextInsightResponse> {
    const qs = new URLSearchParams({ screen });
    if (branch_id) qs.set("branch_id", branch_id);
    return request(`/api/ai/context-insight?${qs}`);
  },
};
