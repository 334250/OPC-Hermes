const API_BASE = '/api'
const HERMES_API_BASE = '/hermes-api/api'

// ── TypeScript Interfaces ───────────────────────────────────────────────

export interface DashboardStats {
  active_tasks: number
  total_workers: number
  avg_quality: number
  pending_proposals: number
  recent_evaluations: number
}

export interface QualityTrendPoint {
  date: string
  worker_id: string
  scores: Record<string, number>
}

export interface DashboardResponse {
  stats: DashboardStats
  quality_trend: QualityTrendPoint[]
}

export interface AgentSummary {
  id: string
  display_name: string
  description: string
  role: 'leader' | 'worker' | 'evaluator'
  capabilities: string[]
  skill_ids: string[]
  default_model: string
  model_tier: string
  toolsets: string[]
  quality_score: number
  total_tasks: number
  successful_tasks: number
  success_rate: number
}

export interface AgentsResponse { agents: AgentSummary[] }

export interface SkillInfo {
  id: string; display_name: string; description: string; tags: string[]
}

export interface EvaluationEntry {
  task_id: string; scores: Record<string, number>; notes: string; evaluated_at: string
}

export interface ScoreTrendPoint { date: string; score: number }

export interface AgentDetailResponse {
  agent: AgentSummary
  skills: SkillInfo[]
  evaluations: EvaluationEntry[]
  score_trend: ScoreTrendPoint[]
}

export interface TaskSummary {
  task_id: string
  status: 'completed' | 'partial' | 'pending'
  workers: string[]
  total_steps: number
  completed_steps: number
  last_activity: string
}

export interface TasksResponse { tasks: TaskSummary[] }

export interface DAGNode {
  id: string; worker_id: string; step_index: number; prompt: string
  status: string; complexity: string; model: string; label: string
}

export interface DAGEdge {
  id: string; source: string; target: string
}

export interface TaskStep {
  worker_id: string; step_index: number; prompt: string
  complexity: string; model: string; upstream: number[]
  expected_output_format: string
  reports: {
    status: string; summary: string; output_preview: string
    tool_call_count: number; error_message: string; reported_at: string
  }[]
}

export interface TaskDetailResponse {
  task_id: string
  steps: TaskStep[]
  dag: { nodes: DAGNode[]; edges: DAGEdge[] }
  artifacts: Record<string, any>
}

export interface MemoryProtocol {
  worker_id: string; prompt: string; step_index: number
  complexity: string; model: string
}

export interface MemoryReport {
  worker_id: string; status: string; summary: string; reported_at: string
}

export interface ProjectMemoryData {
  partition: 'project'; task_id: string
  protocols: MemoryProtocol[]; reports: MemoryReport[]
}

export interface EvalMemoryData {
  partition: 'eval'
  evaluations: EvaluationEntry[]
}

export interface KBResult {
  id: number; title: string; content: string; source_url: string
  source_type: string; tags: string; quality_score: number
}

export interface KBSearchResponse { query: string; results: KBResult[] }

export interface ProposalData {
  id: string; type: string; worker_id: string; title: string
  description: string; current_state: any; proposed_state: any
  evidence: any; risk: string; status: string
  created_at: string; approved_at: string; applied_at: string
}

export interface ProposalsResponse { proposals: ProposalData[]; status_filter: string }

export interface HermesStatusResponse {
  version: string
  release_date?: string
  hermes_home: string
  config_path: string
  env_path: string
  gateway_running: boolean
  gateway_state: string | null
  gateway_pid: number | null
  active_sessions: number
}

export interface HermesSessionInfo {
  id: string
  source: string | null
  model: string | null
  title: string | null
  started_at: number
  ended_at: number | null
  last_active: number
  is_active: boolean
  message_count: number
  tool_call_count: number
  input_tokens: number
  output_tokens: number
  preview: string | null
  parent_session_id?: string | null
}

export interface HermesSessionsResponse {
  sessions: HermesSessionInfo[]
  total: number
  limit: number
  offset: number
}

export interface HermesSessionMessage {
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string | null
  tool_calls?: Array<{ id: string; function: { name: string; arguments: string } }>
  tool_name?: string
  timestamp?: number
}

export interface HermesSessionMessagesResponse {
  session_id: string
  messages: HermesSessionMessage[]
}

export interface HermesSessionSearchResponse {
  results: Array<{
    session_id: string
    snippet: string
    role: string | null
    source: string | null
    model: string | null
    session_started: number | null
  }>
}

export interface HermesLogsResponse {
  file: string
  lines: string[]
}

export interface HermesModelInfoResponse {
  model: string
  provider: string
  auto_context_length: number
  config_context_length: number
  effective_context_length: number
  capabilities: {
    supports_tools?: boolean
    supports_vision?: boolean
    supports_reasoning?: boolean
    context_window?: number
    max_output_tokens?: number
    model_family?: string
  }
}

export interface HermesModelOptionProvider {
  name: string
  slug: string
  models?: string[]
  total_models?: number
  is_current?: boolean
  is_user_defined?: boolean
  source?: string
  warning?: string
}

export interface HermesModelOptionsResponse {
  model?: string
  provider?: string
  providers?: HermesModelOptionProvider[]
}

export interface HermesAuxiliaryModelsResponse {
  main: { provider: string; model: string }
  tasks: Array<{ task: string; provider: string; model: string; base_url: string }>
}

export interface HermesEnvVarInfo {
  is_set: boolean
  redacted_value: string | null
  description: string
  url: string | null
  category: string
  is_password: boolean
  tools: string[]
  advanced: boolean
}

export interface HermesCronJob {
  id: string
  profile?: string | null
  profile_name?: string | null
  name?: string | null
  prompt?: string | null
  script?: string | null
  schedule?: { kind?: string; expr?: string; display?: string }
  schedule_display?: string | null
  enabled: boolean
  state?: string | null
  deliver?: string | null
  last_run_at?: string | null
  next_run_at?: string | null
  last_error?: string | null
}

export interface HermesSkillInfo {
  name: string
  description: string
  category: string
  enabled: boolean
}

export interface HermesToolsetInfo {
  name: string
  label: string
  description: string
  enabled: boolean
  configured: boolean
  tools: string[]
}

export interface HermesPluginInfo {
  name: string
  label: string
  description: string
  icon: string
  version: string
  tab: { path: string; position?: string; override?: string; hidden?: boolean }
  slots?: string[]
  entry: string
  css?: string | null
  has_api: boolean
  source: string
}

export interface HermesOAuthProvidersResponse {
  providers: Array<{
    id: string
    name: string
    flow: 'pkce' | 'device_code' | 'external'
    cli_command: string
    docs_url: string
    status: {
      logged_in: boolean
      source?: string | null
      source_label?: string | null
      token_preview?: string | null
      expires_at?: string | null
      has_refresh_token?: boolean
      error?: string
    }
  }>
}

export interface HermesChatConfigResponse {
  enabled: boolean
  token: string
  pty_path: string
  events_path: string
}

// ── API Client ───────────────────────────────────────────────────────────

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || err.message || `HTTP ${res.status}`)
  }
  return res.json()
}

async function hermesRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${HERMES_API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || err.message || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  dashboard: () => request<DashboardResponse>('/dashboard'),

  listAgents: (role?: string) => request<AgentsResponse>(`/agents${role ? `?role=${role}` : ''}`),
  getAgent: (id: string) => request<AgentDetailResponse>(`/agents/${id}`),
  getAgentEvaluations: (id: string, limit = 50) =>
    request<{ agent_id: string; evaluations: EvaluationEntry[] }>(`/agents/${id}/evaluations?limit=${limit}`),

  getTask: (taskId: string) => request<TaskDetailResponse>(`/tasks/${taskId}`),
  listTasks: () => request<TasksResponse>('/tasks'),

  browseMemory: <T = ProjectMemoryData | EvalMemoryData>(partition: string, taskId?: string, workerId?: string) =>
    request<T>(`/memory/${partition}${taskId ? `?task_id=${taskId}` : ''}${workerId ? `&worker_id=${workerId}` : ''}`),

  searchKnowledge: (q: string) => request<KBSearchResponse>(`/knowledge/search?q=${encodeURIComponent(q)}`),
  ingestKnowledge: (title: string, content: string, tags?: string) =>
    request<any>('/knowledge/ingest', {
      method: 'POST',
      body: JSON.stringify({ title, content, tags }),
    }),

  listArtifacts: (taskId?: string) => request<{ task_id?: string; artifacts: Record<string, any> }>(`/artifacts${taskId ? `?task_id=${taskId}` : ''}`),

  listProposals: (status?: string) => request<ProposalsResponse>(`/proposals${status ? `?status=${status}` : ''}`),
  approveProposal: (id: string) => request<{ status: string; proposal_id: string }>(`/proposals/${id}/approve`, { method: 'POST' }),
  rejectProposal: (id: string) => request<{ status: string; proposal_id: string }>(`/proposals/${id}/reject`, { method: 'POST' }),
  triggerOptimizerScan: () => request<{ scan_time: string; proposals_generated: number }>('/optimizer/scan', { method: 'POST' }),

  getConfig: () => request<{ config: Record<string, any> }>('/config'),
  updateConfig: (updates: Record<string, any>) => request<{ status: string }>('/config', {
    method: 'POST',
    body: JSON.stringify(updates),
  }),

  hermesChatConfig: () => request<HermesChatConfigResponse>('/hermes/chat-config'),
  hermes: <T = any>(path: string, options?: RequestInit) => hermesRequest<T>(path, options),
  hermesStatus: () => hermesRequest<HermesStatusResponse>('/status'),
  hermesSessions: (limit = 30, offset = 0) =>
    hermesRequest<HermesSessionsResponse>(`/sessions?limit=${limit}&offset=${offset}`),
  hermesSearchSessions: (q: string, limit = 20) =>
    hermesRequest<HermesSessionSearchResponse>(`/sessions/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  hermesSessionMessages: (id: string) =>
    hermesRequest<HermesSessionMessagesResponse>(`/sessions/${encodeURIComponent(id)}/messages`),
  hermesDeleteSession: (id: string) =>
    hermesRequest<{ ok: boolean }>(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  hermesLogs: (params: { lines?: number; level?: string; component?: string; file?: string } = {}) => {
    const qs = new URLSearchParams()
    if (params.lines) qs.set('lines', String(params.lines))
    if (params.level && params.level !== 'ALL') qs.set('level', params.level)
    if (params.component && params.component !== 'all') qs.set('component', params.component)
    if (params.file) qs.set('file', params.file)
    return hermesRequest<HermesLogsResponse>(`/logs?${qs.toString()}`)
  },
  hermesModelInfo: () => hermesRequest<HermesModelInfoResponse>('/model/info'),
  hermesModelOptions: () => hermesRequest<HermesModelOptionsResponse>('/model/options'),
  hermesAuxiliaryModels: () => hermesRequest<HermesAuxiliaryModelsResponse>('/model/auxiliary'),
  hermesSetModel: (body: { scope: 'main' | 'auxiliary'; provider: string; model: string; task?: string }) =>
    hermesRequest<{ ok: boolean }>('/model/set', { method: 'POST', body: JSON.stringify(body) }),
  hermesConfig: () => hermesRequest<Record<string, any>>('/config'),
  hermesConfigDefaults: () => hermesRequest<Record<string, any>>('/config/defaults'),
  hermesConfigSchema: () => hermesRequest<{ fields: Record<string, any>; category_order: string[] }>('/config/schema'),
  hermesSaveConfig: (config: Record<string, any>) =>
    hermesRequest<{ ok: boolean }>('/config', { method: 'PUT', body: JSON.stringify({ config }) }),
  hermesEnv: () => hermesRequest<Record<string, HermesEnvVarInfo>>('/env'),
  hermesSetEnv: (key: string, value: string) =>
    hermesRequest<{ ok: boolean; key: string }>('/env', { method: 'PUT', body: JSON.stringify({ key, value }) }),
  hermesDeleteEnv: (key: string) =>
    hermesRequest<{ ok: boolean; key: string }>('/env', { method: 'DELETE', body: JSON.stringify({ key }) }),
  hermesOAuthProviders: () => hermesRequest<HermesOAuthProvidersResponse>('/providers/oauth'),
  hermesCronJobs: (profile = 'all') =>
    hermesRequest<HermesCronJob[]>(`/cron/jobs?profile=${encodeURIComponent(profile)}`),
  hermesCreateCronJob: (job: { prompt: string; schedule: string; name?: string; deliver?: string }, profile = 'default') =>
    hermesRequest<HermesCronJob>(`/cron/jobs?profile=${encodeURIComponent(profile)}`, { method: 'POST', body: JSON.stringify(job) }),
  hermesPauseCronJob: (id: string, profile = 'default') =>
    hermesRequest<HermesCronJob>(`/cron/jobs/${encodeURIComponent(id)}/pause?profile=${encodeURIComponent(profile)}`, { method: 'POST' }),
  hermesResumeCronJob: (id: string, profile = 'default') =>
    hermesRequest<HermesCronJob>(`/cron/jobs/${encodeURIComponent(id)}/resume?profile=${encodeURIComponent(profile)}`, { method: 'POST' }),
  hermesTriggerCronJob: (id: string, profile = 'default') =>
    hermesRequest<HermesCronJob>(`/cron/jobs/${encodeURIComponent(id)}/trigger?profile=${encodeURIComponent(profile)}`, { method: 'POST' }),
  hermesDeleteCronJob: (id: string, profile = 'default') =>
    hermesRequest<{ ok: boolean }>(`/cron/jobs/${encodeURIComponent(id)}?profile=${encodeURIComponent(profile)}`, { method: 'DELETE' }),
  hermesSkills: () => hermesRequest<HermesSkillInfo[]>('/skills'),
  hermesToggleSkill: (name: string, enabled: boolean) =>
    hermesRequest<{ ok: boolean }>('/skills/toggle', { method: 'PUT', body: JSON.stringify({ name, enabled }) }),
  hermesToolsets: () => hermesRequest<HermesToolsetInfo[]>('/tools/toolsets'),
  hermesPlugins: () => hermesRequest<HermesPluginInfo[]>('/dashboard/plugins'),
  hermesRescanPlugins: () => hermesRequest<{ ok: boolean; count: number }>('/dashboard/plugins/rescan'),
  hermesSetPluginVisibility: (name: string, hidden: boolean) =>
    hermesRequest<{ ok: boolean; name: string; hidden: boolean }>(
      `/dashboard/plugins/${name.split('/').map(encodeURIComponent).join('/')}/visibility`,
      { method: 'POST', body: JSON.stringify({ hidden }) },
    ),

  health: () => request<{ status: string; version: string; timestamp: string }>('/health'),
}
