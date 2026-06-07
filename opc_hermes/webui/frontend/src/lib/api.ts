const API_BASE = '/api'

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

  health: () => request<{ status: string; version: string; timestamp: string }>('/health'),
}
