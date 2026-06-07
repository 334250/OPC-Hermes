const API_BASE = '/api'

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
  // Dashboard
  dashboard: () => request<any>('/dashboard'),

  // Agents
  listAgents: (role?: string) => request<any>(`/agents${role ? `?role=${role}` : ''}`),
  getAgent: (id: string) => request<any>(`/agents/${id}`),
  getAgentEvaluations: (id: string, limit = 50) => request<any>(`/agents/${id}/evaluations?limit=${limit}`),

  // Tasks
  getTask: (taskId: string) => request<any>(`/tasks/${taskId}`),

  // Memory
  browseMemory: (partition: string, taskId?: string, workerId?: string) =>
    request<any>(`/memory/${partition}${taskId ? `?task_id=${taskId}` : ''}${workerId ? `&worker_id=${workerId}` : ''}`),

  // Knowledge
  searchKnowledge: (q: string) => request<any>(`/knowledge/search?q=${encodeURIComponent(q)}`),
  ingestKnowledge: (title: string, content: string, tags?: string) =>
    request<any>('/knowledge/ingest', {
      method: 'POST',
      body: JSON.stringify({ title, content, tags }),
    }),

  // Artifacts
  listArtifacts: (taskId?: string) => request<any>(`/artifacts${taskId ? `?task_id=${taskId}` : ''}`),

  // Proposals
  listProposals: (status?: string) => request<any>(`/proposals${status ? `?status=${status}` : ''}`),
  approveProposal: (id: string) => request<any>(`/proposals/${id}/approve`, { method: 'POST' }),
  rejectProposal: (id: string) => request<any>(`/proposals/${id}/reject`, { method: 'POST' }),
  triggerOptimizerScan: () => request<any>('/optimizer/scan', { method: 'POST' }),

  // Config
  getConfig: () => request<any>('/config'),
  updateConfig: (updates: Record<string, any>) => request<any>('/config', {
    method: 'POST',
    body: JSON.stringify(updates),
  }),

  // Health
  health: () => request<any>('/health'),
}
