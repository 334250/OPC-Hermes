import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

const roleFilters = [
  { labelKey: 'all', value: '' },
  { labelKey: 'leader', value: 'leader' },
  { labelKey: 'worker', value: 'worker' },
  { labelKey: 'evaluator', value: 'evaluator' },
]

export default function AgentList() {
  const { t } = useI18n()
  const [agents, setAgents] = useState<any[]>([])
  const [role, setRole] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.listAgents(role || undefined)
      .then(d => setAgents(d.agents ?? []))
      .finally(() => setLoading(false))
  }, [role])

  const filtered = agents.filter(a =>
    !search || a.display_name.toLowerCase().includes(search.toLowerCase()) || a.id.toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <AgentSkeleton />

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">{t('agents')}</h2>

      {/* Filters */}
      <div className="flex gap-3 mb-6">
        <input
          className="input flex-1 max-w-sm"
          placeholder={t('searchAgents')}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <div className="flex gap-1">
          {roleFilters.map(r => (
            <button
              key={r.value}
              onClick={() => setRole(r.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                role === r.value ? 'bg-opc-accent text-white' : 'bg-opc-surface-2 text-opc-text-2 hover:text-opc-text'
              }`}
            >
              {t(r.labelKey)}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-3 gap-4">
        {filtered.map(agent => (
          <Link to={`/agents/${agent.id}`} key={agent.id} className="card group">
            <div className="flex items-center gap-3 mb-3">
              <span className="text-xl">{roleIcon(agent.role)}</span>
              <div>
                <div className="text-sm font-medium text-opc-text group-hover:text-opc-accent transition-colors">{agent.display_name}</div>
                <div className="text-xs text-opc-text-2">{agent.id}</div>
              </div>
            </div>
            <div className="flex items-center gap-2 mb-3">
              <span className={`badge-${roleBadgeColor(agent.role)}`}>{agent.role}</span>
              <span className="badge-accent">{agent.model_tier}</span>
              {agent.quality_score > 0 && (
                <span className="text-xs text-opc-text-2 ml-auto">⭐ {(agent.quality_score * 100).toFixed(0)}%</span>
              )}
            </div>
            <p className="text-xs text-opc-text-2 line-clamp-2">{agent.description}</p>
            <div className="flex gap-2 mt-3 text-xs text-opc-text-2">
              <span>{agent.skill_ids?.length ?? 0} {t('skills')}</span>
              <span>·</span>
              <span>{agent.success_rate ? `${(agent.success_rate * 100).toFixed(0)}% ${t('success')}` : t('noData')}</span>
            </div>
          </Link>
        ))}
      </div>

      {filtered.length === 0 && !loading && (
        <div className="py-16 text-center text-opc-text-2 text-sm">{t('noAgentsFound')}</div>
      )}
    </div>
  )
}

function roleIcon(role: string) {
  return { leader: '👑', worker: '🔧', evaluator: '🔍' }[role] ?? '❓'
}
function roleBadgeColor(role: string) {
  return { leader: 'accent', worker: 'info', evaluator: 'success' }[role] ?? 'info'
}

function AgentSkeleton() {
  return (
    <div>
      <div className="h-7 w-32 bg-opc-surface-2 rounded mb-6 animate-pulse" />
      <div className="grid grid-cols-3 gap-4">
        {[1, 2, 3, 4, 5, 6].map(i => (
          <div key={i} className="card animate-pulse">
            <div className="flex gap-3 mb-3">
              <div className="w-8 h-8 bg-opc-surface-2 rounded-full" />
              <div>
                <div className="h-4 w-24 bg-opc-surface-2 rounded mb-1" />
                <div className="h-3 w-16 bg-opc-surface-2 rounded opacity-50" />
              </div>
            </div>
            <div className="h-3 w-full bg-opc-surface-2 rounded opacity-30 mb-2" />
            <div className="h-3 w-2/3 bg-opc-surface-2 rounded opacity-20" />
          </div>
        ))}
      </div>
    </div>
  )
}
