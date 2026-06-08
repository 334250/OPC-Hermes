import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

export default function AgentDetail() {
  const { t } = useI18n()
  const { agentId } = useParams<{ agentId: string }>()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!agentId) return
    setLoading(true)
    api.getAgent(agentId).then(setData).finally(() => setLoading(false))
  }, [agentId])

  if (loading) return <div className="card animate-pulse"><div className="h-64 bg-opc-surface-2 rounded" /></div>
  if (!data) return <div className="text-opc-text-2">{t('agentNotFound')}</div>

  const agent = data.agent

  return (
    <div>
      <Link to="/agents" className="text-sm text-opc-text-2 hover:text-opc-text mb-4 inline-block">← {t('backToAgents')}</Link>
      <div className="flex items-center gap-4 mb-6">
        <span className="text-3xl">{roleIcon(agent.role)}</span>
        <div>
          <h2 className="text-xl font-semibold">{agent.display_name}</h2>
          <p className="text-sm text-opc-text-2">{agent.id} · {agent.role} · {agent.model_tier}</p>
        </div>
        <div className="ml-auto text-right">
          <div className="text-2xl font-semibold text-opc-accent">{agent.quality_score > 0 ? `${(agent.quality_score * 100).toFixed(0)}%` : '—'}</div>
          <div className="text-xs text-opc-text-2">{t('qualityScore')}</div>
        </div>
      </div>

      <p className="text-sm text-opc-text-2 mb-6">{agent.description}</p>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <StatBox label={t('tasks')} value={agent.total_tasks} />
        <StatBox label={t('success')} value={agent.success_rate ? `${(agent.success_rate * 100).toFixed(0)}%` : '—'} />
        <StatBox label={t('model')} value={agent.default_model || 'default'} />
        <StatBox label={t('skills')} value={agent.skill_ids?.length ?? 0} />
      </div>

      {/* Skills */}
      <div className="card mb-6">
        <h3 className="text-sm font-semibold text-opc-text-2 uppercase tracking-wider mb-3">{t('skills')}</h3>
        <div className="flex flex-wrap gap-2">
          {data.skills?.map((s: any) => (
            <span key={s.id} className="badge-accent cursor-default" title={s.description}>{s.display_name}</span>
          ))}
          {!data.skills?.length && <span className="text-xs text-opc-text-2">{t('noSkills')}</span>}
        </div>
      </div>

      {/* Evaluations */}
      <div className="card mb-6">
        <h3 className="text-sm font-semibold text-opc-text-2 uppercase tracking-wider mb-3">{t('recentEvaluations')}</h3>
        {data.evaluations?.length ? (
          <div className="space-y-2">
            {data.evaluations.slice(0, 10).map((e: any) => {
              const avg = Object.values(e.scores || {}).length
                ? (Object.values(e.scores) as number[]).reduce((a: number, b: number) => a + b, 0) / Object.values(e.scores).length
                : 0
              return (
                <div key={e.task_id} className="flex items-center justify-between py-2 border-b border-opc-border last:border-0 text-sm">
                  <span className="text-opc-text-2 truncate max-w-xs">{e.task_id}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-opc-text-2">{e.evaluated_at?.slice(0, 10)}</span>
                    <span className={`badge-${avg >= 0.7 ? 'success' : avg >= 0.5 ? 'warning' : 'error'}`}>
                      {(avg * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="py-8 text-center text-opc-text-2 text-sm">{t('noEvaluationsYet')}</div>
        )}
      </div>

      {/* Score Trend */}
      <div className="card">
        <h3 className="text-sm font-semibold text-opc-text-2 uppercase tracking-wider mb-3">{t('scoreTrend')}</h3>
        {data.score_trend?.length ? (
          <div className="h-32 flex items-end gap-0.5">
            {data.score_trend.slice(-30).map((d: any, i: number) => (
              <div
                key={i}
                className="flex-1 bg-opc-accent/30 rounded-t"
                style={{ height: `${d.score * 100}%`, minHeight: 2 }}
                title={`${d.date?.slice(0, 10)}: ${(d.score * 100).toFixed(0)}%`}
              />
            ))}
          </div>
        ) : (
          <div className="py-8 text-center text-opc-text-2 text-sm">{t('noTrendData')}</div>
        )}
      </div>
    </div>
  )
}

function StatBox({ label, value }: { label: string; value: any }) {
  return (
    <div className="card text-center py-3">
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-xs text-opc-text-2">{label}</div>
    </div>
  )
}

function roleIcon(role: string) { return { leader: '👑', worker: '🔧', evaluator: '🔍' }[role] ?? '❓' }
