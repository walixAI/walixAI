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

export interface BotConfigOut {
  onboarding_status: string;
  bot_name: string | null;
  industry: string | null;
  branch_name: string;
  business_description: string | null;
  latest_draft_id: string | null;
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
  current_score: number | null;
  current_score_trend: string | null;
}

export interface ScoreHistoryItem {
  id: string;
  score: number;
  main_reason: string;
  calculated_at: string;
  positive_factors: { items?: string[] };
  negative_factors: { items?: string[] };
}

export interface LeadScoreOut {
  current_score: number | null;
  current_score_trend: string | null;
  history: ScoreHistoryItem[];
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

// ── Dashboard types (role-specific) ──────────────────────────────────────────

export interface DashboardLeadItem {
  id: string;
  name: string | null;
  wa_phone: string;
  status: string;
  sentiment: string;
  current_score: number | null;
  current_score_trend: number | null;
  stage_name: string | null;
  updated_at: string;
}

export interface DashboardActivity {
  activity_type: string;
  lead_id: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface DashboardSuggestion {
  id: string;
  agent_type: string;
  suggestion_text: string;
  created_at: string;
}

export interface MiniPipelineItem {
  stage_id: string | null;
  stage_name: string | null;
  count: number;
}

export interface DashboardAsesor {
  role: "asesor";
  my_leads: DashboardLeadItem[];
  recent_activity: DashboardActivity[];
  pending_suggestions: DashboardSuggestion[];
  mini_pipeline: MiniPipelineItem[];
}

export interface TeamPerformanceItem {
  asesor_id: string;
  name: string;
  leads_assigned: number;
  leads_won: number;
  conversion_rate: number;
}

export interface SentimentSummary {
  overall_score: number | null;
  distribution: Record<string, { count: number; pct: number }>;
  snapshot_date: string | null;
}

export interface AtRiskLead {
  lead_id: string;
  name: string | null;
  score: number;
  stage_name: string | null;
}

export interface DashboardGerente {
  role: "gerente";
  pipeline: {
    total_active: number;
    by_stage: Array<{ stage_id: string | null; stage_name: string | null; count: number; avg_score: number | null }>;
  };
  team_performance: TeamPerformanceItem[];
  sentiment_summary: SentimentSummary;
  at_risk_leads: AtRiskLead[];
  active_automations: number;
}

export interface BranchMetrics {
  branch_id: string;
  branch_name: string;
  leads_active: number;
  leads_created_month: number;
  leads_won_month: number;
  conversion_rate: number;
  sentiment_score: number | null;
}

export interface ConversionPeriod {
  created: number;
  won: number;
  rate: number;
}

export interface DashboardOwner {
  role: "owner";
  branches: BranchMetrics[];
  mrr_estimate: number;
  conversion_comparison: { this_month: ConversionPeriod; last_month: ConversionPeriod };
  cross_branch_suggestions: DashboardSuggestion[];
}

export interface DashboardIT {
  role: "it";
  integrations: { total_branches: number; branches_with_wa: number; branches_without_wa: number };
  ai_command_logs_24h: number;
  webhook_errors_24h: number;
  ai_token_usage_month: number;
  config_alerts: Array<{ type: string; branch_id: string; branch_name: string }>;
}

export type DashboardData = DashboardAsesor | DashboardGerente | DashboardOwner | DashboardIT;

// ── Metrics types ─────────────────────────────────────────────────────────────

export interface PeriodSummary {
  leads_created: number;
  leads_qualified: number;
  leads_won: number;
  leads_lost: number;
  messages_sent: number;
  messages_received: number;
  calls_logged: number;
  tasks_completed: number;
  quotes_sent: number;
  avg_first_response_sec: number;
  conversion_rate: number;
}

export interface DailyMetricOut {
  metric_date: string;
  leads_created: number;
  leads_qualified: number;
  leads_won: number;
  leads_lost: number;
  messages_sent: number;
  messages_received: number;
  avg_first_response_sec: number;
}

export interface DeltaEntry {
  current: number;
  previous: number;
  diff: number;
  pct_change: number | null;
}

export interface MetricsDashboard {
  period: string;
  branch_id: string;
  current: PeriodSummary;
  previous: PeriodSummary | null;
  delta: Record<string, DeltaEntry> | null;
  daily: DailyMetricOut[];
}

export interface SentimentSnapshotOut {
  snapshot_date: string;
  overall_score: number;
  distribution: Record<string, { count: number; pct: number }>;
  by_stage: Record<string, number>;
  by_agent: Record<string, number>;
}

export interface SentimentOut {
  current: SentimentSnapshotOut | null;
  trend: number | null;
  insight: string;
}

export interface ForecastLeadOut {
  lead_id: string;
  name: string | null;
  wa_phone: string;
  score: number;
  stage_name: string | null;
}

export interface ForecastOut {
  pipeline_forecast: { high: number; medium: number; low: number };
  high_probability_leads: ForecastLeadOut[];
  at_risk_leads: ForecastLeadOut[];
}

// ── Agent suggestion types ────────────────────────────────────────────────────

export interface AgentSuggestion {
  id: string;
  agent_type: string;
  trigger_description: string;
  suggestion_text: string;
  action_payload: Record<string, unknown> | null;
  target_role: string;
  target_user_id: string | null;
  status: "suggested" | "accepted" | "confirmed" | "dismissed" | "executed" | "failed" | "expired";
  execution_result: Record<string, unknown> | null;
  error_detail: string | null;
  responded_at: string | null;
  expires_at: string;
  created_at: string;
  updated_at: string;
}

// ── Automation types ──────────────────────────────────────────────────────────

export type AutomationOut = AgentSuggestion;

export interface AutomationListResponse {
  items: AutomationOut[];
  total: number;
  page: number;
  limit: number;
}

// ── AI Bar types ──────────────────────────────────────────────────────────────

export interface AICommandRequest {
  message: string;
  context: Record<string, unknown>;
  history: Array<{ role: "user" | "assistant"; content: string }>;
}

export interface ContactInfo {
  id: string;
  name?: string | null;
  lastName?: string | null;
  company?: string | null;
  phone?: string | null;
  status?: string;
}

export interface AIActionData {
  action: string;
  contact?: ContactInfo;
  contacts?: ContactInfo[];
  total?: number;
  contactId?: string;
  contactName?: string;
  activityType?: string;
  emoji?: string;
  confirmationId?: string;
  confirmAction?: string;
  filtersApplied?: Record<string, unknown>;
  navigateTo?: string;
  message?: string;
}

export interface AICommandResponse {
  intent_type: string;
  response_text: string;
  requires_confirmation: boolean;
  actions_taken: Array<{ type: string; success: boolean; error?: string; result?: Record<string, unknown> | null }>;
  suggested_actions: string[];
  action_data: AIActionData | null;
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

  async register(data: {
    name: string;
    email: string;
    password: string;
  }): Promise<{ access_token: string; user: WalixUser }> {
    return request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
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

  async getBotConfig(branchId: string): Promise<BotConfigOut> {
    return request(`/api/branches/${branchId}/bot-config`);
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

  // Lead scoring
  async getLeadScore(leadId: string): Promise<LeadScoreOut> {
    return request(`/api/leads/${leadId}/score`);
  },

  async recalculateLeadScore(leadId: string): Promise<ScoreHistoryItem & { current_score_trend: string }> {
    return request(`/api/leads/${leadId}/score/recalculate`, { method: "POST" });
  },

  // Dashboard (role-aware)
  async getDashboard(branch_id?: string): Promise<DashboardData> {
    const qs = branch_id ? `?branch_id=${branch_id}` : "";
    return request(`/api/dashboard${qs}`);
  },

  // Metrics
  async getMetricsDashboard(params: {
    period?: "week" | "month" | "quarter";
    compare?: boolean;
    branch_id?: string;
  } = {}): Promise<MetricsDashboard> {
    const qs = new URLSearchParams();
    if (params.period) qs.set("period", params.period);
    if (params.compare != null) qs.set("compare", String(params.compare));
    if (params.branch_id) qs.set("branch_id", params.branch_id);
    const q = qs.toString() ? `?${qs}` : "";
    return request(`/api/metrics/dashboard${q}`);
  },

  async getSentiment(params: { branch_id?: string; days?: number } = {}): Promise<SentimentOut> {
    const qs = new URLSearchParams();
    if (params.branch_id) qs.set("branch_id", params.branch_id);
    if (params.days != null) qs.set("days", String(params.days));
    const q = qs.toString() ? `?${qs}` : "";
    return request(`/api/metrics/sentiment${q}`);
  },

  async getForecast(branch_id?: string): Promise<ForecastOut> {
    const qs = branch_id ? `?branch_id=${branch_id}` : "";
    return request(`/api/metrics/forecast${qs}`);
  },

  // Agent suggestions
  async getAgentSuggestions(): Promise<AgentSuggestion[]> {
    return request("/api/agents/suggestions");
  },

  async confirmSuggestion(id: string): Promise<AgentSuggestion> {
    return request(`/api/agents/suggestions/${id}/confirm`, { method: "POST" });
  },

  async dismissSuggestion(id: string, reason?: string): Promise<AgentSuggestion> {
    return request(`/api/agents/suggestions/${id}/dismiss`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    });
  },

  // Automations
  async getAutomations(params: {
    page?: number;
    limit?: number;
    status?: string;
    agent_type?: string;
  } = {}): Promise<AutomationListResponse> {
    const qs = new URLSearchParams();
    if (params.page != null) qs.set("page", String(params.page));
    if (params.limit != null) qs.set("limit", String(params.limit));
    if (params.status) qs.set("status", params.status);
    if (params.agent_type) qs.set("agent_type", params.agent_type);
    const q = qs.toString() ? `?${qs}` : "";
    return request(`/api/automations${q}`);
  },

  async updateAutomation(id: string, data: { is_active?: boolean; custom_message?: string }): Promise<AutomationOut> {
    return request(`/api/automations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async reExecuteAutomation(id: string): Promise<AutomationOut> {
    return request(`/api/automations/${id}/re-execute`, { method: "POST" });
  },
};
