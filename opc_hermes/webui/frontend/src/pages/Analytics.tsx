import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type AnalyticsModelUsage, type AnalyticsResponse } from '../lib/api'
import { useI18n } from '../lib/i18n'

type LoadState = 'loading' | 'ready' | 'error'

type ModelRow = {
  model: string
  provider: string
  sessions: number
  tokens: number
  cost: number
  api_calls: number
  tool_calls: number
  avg_tokens_per_session: number
  last_used_at: number | string | null
}

const statusClass: Record<string, string> = {
  completed: 'badge-success',
  active: 'badge-info',
  partial: 'badge-warning',
  pending: 'badge',
  failed: 'badge-error',
  blocked: 'badge-warning',
}

function formatNumber(value: number | null | undefined) {
  return new Intl.NumberFormat().format(Math.round(value || 0))
}

function formatCompact(value: number | null | undefined) {
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value || 0)
}

function formatCost(value: number | null | undefined) {
  const amount = value || 0
  if (amount > 0 && amount < 0.01) return `$${amount.toFixed(4)}`
  return `$${amount.toFixed(2)}`
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  return `${Math.round(value * 100)}%`
}

function formatTime(value: number | string | null | undefined) {
  if (!value) return '-'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}

function shortDay(day: string) {
  if (!day) return '-'
  const parts = day.split('-')
  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : day
}

function totalTokens(row: { input_tokens?: number; output_tokens?: number; cache_read_tokens?: number; reasoning_tokens?: number }) {
  return (row.input_tokens || 0) + (row.output_tokens || 0) + (row.cache_read_tokens || 0) + (row.reasoning_tokens || 0)
}

function KpiCard({ label, value, detail, tone = 'text-opc-text' }: { label: string; value: string; detail?: string; tone?: string }) {
  return (
    <div className="card">
      <div className={`text-2xl font-semibold ${tone}`}>{value}</div>
      <div className="stat-label">{label}</div>
      {detail && <div className="mt-3 text-xs text-opc-text-2">{detail}</div>}
    </div>
  )
}

function EmptyBlock({ label }: { label: string }) {
  return <div className="py-12 text-center text-sm text-opc-text-2">{label}</div>
}

function BarRows<T>({
  rows,
  value,
  label,
  meta,
  tone = 'bg-opc-accent',
}: {
  rows: T[]
  value: (row: T) => number
  label: (row: T) => string
  meta?: (row: T) => string
  tone?: string
}) {
  const max = Math.max(1, ...rows.map(value))
  if (!rows.length) return <EmptyBlock label="No data" />
  return (
    <div className="space-y-3">
      {rows.map((row, index) => {
        const amount = value(row)
        return (
          <div key={`${label(row)}-${index}`} className="grid grid-cols-[88px_minmax(0,1fr)_72px] items-center gap-3 text-xs">
            <div className="truncate text-opc-text-2">{label(row)}</div>
            <div className="h-2 rounded-full bg-opc-surface-2">
              <div className={`h-2 rounded-full ${tone}`} style={{ width: `${Math.max(3, (amount / max) * 100)}%` }} />
            </div>
            <div className="text-right text-opc-text-2">{meta ? meta(row) : formatCompact(amount)}</div>
          </div>
        )
      })}
    </div>
  )
}

function sourceLabel(source: string) {
  if (source === 'hermes-state') return 'Hermes state.db'
  if (source === 'opc-memory') return 'OPC memory'
  if (source === 'opc-fallback') return 'OPC fallback'
  return source || '-'
}

export default function AnalyticsPage() {
  const { lang, t } = useI18n()
  const [days, setDays] = useState(30)
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [data, setData] = useState<AnalyticsResponse | null>(null)

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      const next = await api.analytics(days)
      setData(next)
      setState('ready')
    } catch (e: any) {
      setError(e.message || String(e))
      setState('error')
    }
  }, [days])

  useEffect(() => { load() }, [load])

  const modelRows = useMemo<ModelRow[]>(() => {
    if (!data) return []
    if (data.models.models.length) {
      return data.models.models.map((row: AnalyticsModelUsage) => ({
        model: row.model,
        provider: row.provider,
        sessions: row.sessions,
        tokens: totalTokens(row),
        cost: row.actual_cost || row.estimated_cost,
        api_calls: row.api_calls,
        tool_calls: row.tool_calls,
        avg_tokens_per_session: row.avg_tokens_per_session,
        last_used_at: row.last_used_at,
      }))
    }
    return data.usage.by_model.map((row) => ({
      model: row.model,
      provider: '',
      sessions: row.sessions,
      tokens: (row.input_tokens || 0) + (row.output_tokens || 0),
      cost: row.estimated_cost,
      api_calls: row.api_calls,
      tool_calls: 0,
      avg_tokens_per_session: row.sessions ? ((row.input_tokens || 0) + (row.output_tokens || 0)) / row.sessions : 0,
      last_used_at: null,
    }))
  }, [data])

  if (state === 'loading') {
    return <div className="card animate-pulse"><div className="h-96 rounded-lg bg-opc-surface-2" /></div>
  }

  if (state === 'error' || !data) {
    return (
      <div className="card border-red-500/30 bg-red-500/5">
        <p className="text-sm text-red-400">{t('failedToLoad')}: {error}</p>
        <button className="btn-primary mt-3 text-xs" onClick={load}>{t('retry')}</button>
      </div>
    )
  }

  const usageTotals = data.usage.totals
  const opcTotals = data.opc.task_totals
  const totalUsageTokens = usageTotals.total_input + usageTotals.total_output + usageTotals.total_cache_read + usageTotals.total_reasoning
  const latestDaily = data.usage.daily.slice(-14)
  const latestOpcDaily = data.opc.daily_activity.slice(-14)
  const topModels = modelRows.slice(0, 10)
  const topWorkers = data.opc.worker_activity.filter((worker) => worker.tasks || worker.reports || worker.avg_quality !== null).slice(0, 8)

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-xl font-semibold">{lang === 'zh' ? '分析' : 'Analytics'}</h2>
          <p className="mt-1 max-w-3xl text-sm text-opc-text-2">
            {lang === 'zh' ? '本地 Hermes 使用量、模型消耗和 OPC 工作流指标。' : 'Local Hermes usage, model consumption, and OPC workflow metrics.'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select className="input w-28 text-xs" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>{lang === 'zh' ? '7 天' : '7 days'}</option>
            <option value={30}>{lang === 'zh' ? '30 天' : '30 days'}</option>
            <option value={90}>{lang === 'zh' ? '90 天' : '90 days'}</option>
          </select>
          <button className="btn-secondary text-xs" onClick={load}>{t('refresh')}</button>
        </div>
      </div>

      {data.sources.warnings.length > 0 && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
          <div className="text-sm font-medium text-yellow-300">{lang === 'zh' ? '部分数据使用兜底来源' : 'Fallback source in use'}</div>
          <div className="mt-2 space-y-1 text-xs text-yellow-100/80">
            {data.sources.warnings.slice(0, 2).map((warning) => <div key={warning}>{warning}</div>)}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          label={lang === 'zh' ? 'Hermes 会话' : 'Hermes Sessions'}
          value={formatNumber(usageTotals.total_sessions)}
          detail={`${formatNumber(usageTotals.total_api_calls)} API calls`}
          tone="text-blue-300"
        />
        <KpiCard
          label={lang === 'zh' ? 'Token 总量' : 'Total Tokens'}
          value={formatCompact(totalUsageTokens)}
          detail={`${formatCompact(usageTotals.total_input)} in / ${formatCompact(usageTotals.total_output)} out`}
          tone="text-green-300"
        />
        <KpiCard
          label={lang === 'zh' ? '估算成本' : 'Estimated Cost'}
          value={formatCost(usageTotals.total_actual_cost || usageTotals.total_estimated_cost)}
          detail={sourceLabel(data.sources.usage)}
          tone="text-yellow-300"
        />
        <KpiCard
          label={lang === 'zh' ? 'OPC 任务' : 'OPC Tasks'}
          value={formatNumber(opcTotals.total)}
          detail={`${formatNumber(opcTotals.completed)} done / ${formatNumber(opcTotals.active)} active`}
          tone="text-cyan-300"
        />
        <KpiCard
          label={lang === 'zh' ? '平均质量' : 'Avg Quality'}
          value={formatPercent(data.opc.avg_quality)}
          detail={`${formatNumber(data.opc.evaluations_total)} evaluations`}
          tone="text-fuchsia-300"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">{lang === 'zh' ? 'Token 趋势' : 'Token Trend'}</h3>
            <span className="text-xs text-opc-text-2">{sourceLabel(data.sources.usage)}</span>
          </div>
          <BarRows
            rows={latestDaily}
            label={(row) => shortDay(row.day)}
            value={(row) => totalTokens(row)}
            meta={(row) => `${formatCompact(totalTokens(row))} · ${row.sessions}`}
            tone="bg-green-400"
          />
        </div>

        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">{lang === 'zh' ? 'OPC 活动' : 'OPC Activity'}</h3>
            <span className="text-xs text-opc-text-2">{sourceLabel(data.sources.opc)}</span>
          </div>
          <BarRows
            rows={latestOpcDaily}
            label={(row) => shortDay(row.day)}
            value={(row) => row.reports + row.evaluations + row.tasks_created}
            meta={(row) => `${row.reports} rep · ${row.evaluations} eval`}
            tone="bg-cyan-400"
          />
        </div>
      </div>

      <div className="card">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">{lang === 'zh' ? '模型使用' : 'Model Usage'}</h3>
          <span className="text-xs text-opc-text-2">{formatNumber(data.models.totals.distinct_models || topModels.length)} models</span>
        </div>
        {topModels.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[780px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-opc-text-2">
                <tr className="border-b border-opc-border">
                  <th className="py-2 pr-4 font-medium">{lang === 'zh' ? '模型' : 'Model'}</th>
                  <th className="py-2 pr-4 font-medium">{lang === 'zh' ? '服务商' : 'Provider'}</th>
                  <th className="py-2 pr-4 text-right font-medium">{lang === 'zh' ? '会话' : 'Sessions'}</th>
                  <th className="py-2 pr-4 text-right font-medium">Tokens</th>
                  <th className="py-2 pr-4 text-right font-medium">Cost</th>
                  <th className="py-2 pr-4 text-right font-medium">Tools</th>
                  <th className="py-2 text-right font-medium">{lang === 'zh' ? '最近使用' : 'Last Used'}</th>
                </tr>
              </thead>
              <tbody>
                {topModels.map((row) => (
                  <tr key={`${row.provider}-${row.model}`} className="border-b border-opc-border/60 last:border-0">
                    <td className="max-w-[260px] truncate py-3 pr-4 font-medium">{row.model}</td>
                    <td className="py-3 pr-4 text-opc-text-2">{row.provider || '-'}</td>
                    <td className="py-3 pr-4 text-right text-opc-text-2">{formatNumber(row.sessions)}</td>
                    <td className="py-3 pr-4 text-right text-opc-text-2">{formatCompact(row.tokens)}</td>
                    <td className="py-3 pr-4 text-right text-opc-text-2">{formatCost(row.cost)}</td>
                    <td className="py-3 pr-4 text-right text-opc-text-2">{formatNumber(row.tool_calls)}</td>
                    <td className="py-3 text-right text-opc-text-2">{formatTime(row.last_used_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyBlock label={lang === 'zh' ? '暂无模型使用数据' : 'No model usage data'} />}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">{lang === 'zh' ? 'Worker 活动' : 'Worker Activity'}</h3>
            <span className="text-xs text-opc-text-2">{formatNumber(data.opc.tool_calls)} tool calls</span>
          </div>
          {topWorkers.length ? (
            <div className="space-y-3">
              {topWorkers.map((worker) => (
                <div key={worker.worker_id} className="rounded-lg border border-opc-border bg-opc-bg p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold">{worker.display_name || worker.worker_id}</div>
                      <div className="mt-1 truncate text-xs text-opc-text-2">{worker.role} · {worker.model || '-'}</div>
                    </div>
                    <span className="badge-info">{formatPercent(worker.avg_quality)}</span>
                  </div>
                  <div className="mt-3 grid grid-cols-4 gap-2 text-xs text-opc-text-2">
                    <span>{worker.tasks} tasks</span>
                    <span>{worker.reports} reports</span>
                    <span>{worker.completed_reports} done</span>
                    <span>{worker.tool_calls} tools</span>
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyBlock label={lang === 'zh' ? '暂无 Worker 活动' : 'No worker activity'} />}
        </div>

        <div className="space-y-4">
          <div className="card">
            <h3 className="mb-4 text-sm font-semibold">{lang === 'zh' ? '任务状态' : 'Task Status'}</h3>
            <div className="grid grid-cols-2 gap-2">
              {(['completed', 'active', 'partial', 'pending', 'failed', 'blocked'] as const).map((key) => (
                <div key={key} className="rounded-lg border border-opc-border bg-opc-bg p-3">
                  <div className="text-lg font-semibold">{formatNumber(opcTotals[key])}</div>
                  <div className="mt-1 text-xs capitalize text-opc-text-2">{key}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h3 className="mb-4 text-sm font-semibold">{lang === 'zh' ? '质量维度' : 'Quality Dimensions'}</h3>
            <BarRows
              rows={data.opc.score_dimensions}
              label={(row) => row.key}
              value={(row) => row.avg}
              meta={(row) => `${formatPercent(row.avg)} · ${row.count}`}
              tone="bg-fuchsia-400"
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">{lang === 'zh' ? '近期任务' : 'Recent Tasks'}</h3>
            <span className="text-xs text-opc-text-2">{formatNumber(opcTotals.total)}</span>
          </div>
          {data.opc.recent_tasks.length ? (
            <div className="space-y-2">
              {data.opc.recent_tasks.slice(0, 8).map((task) => (
                <Link key={task.task_id} className="block rounded-lg border border-opc-border bg-opc-bg p-3 transition-colors hover:border-opc-accent/50" to={`/tasks/${encodeURIComponent(task.task_id)}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{task.task_id}</div>
                      <div className="mt-1 text-xs text-opc-text-2">{task.completed_steps}/{task.total_steps} steps · {task.workers.length} workers</div>
                    </div>
                    <span className={statusClass[task.status] || 'badge'}>{task.status}</span>
                  </div>
                </Link>
              ))}
            </div>
          ) : <EmptyBlock label={lang === 'zh' ? '暂无近期任务' : 'No recent tasks'} />}
        </div>

        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">{lang === 'zh' ? 'OPC 模型分配' : 'OPC Model Assignments'}</h3>
            <span className="text-xs text-opc-text-2">{formatNumber(data.opc.model_assignments.length)}</span>
          </div>
          {data.opc.model_assignments.length ? (
            <div className="space-y-3">
              {data.opc.model_assignments.slice(0, 8).map((row) => (
                <div key={`${row.provider}-${row.model}`} className="grid grid-cols-[minmax(0,1fr)_72px_72px] items-center gap-3 text-sm">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{row.model}</div>
                    <div className="mt-1 truncate text-xs text-opc-text-2">{row.provider || '-'}</div>
                  </div>
                  <div className="text-right text-xs text-opc-text-2">{row.agents} agents</div>
                  <div className="text-right text-xs text-opc-text-2">{row.tasks} tasks</div>
                </div>
              ))}
            </div>
          ) : <EmptyBlock label={lang === 'zh' ? '暂无模型分配' : 'No model assignments'} />}
        </div>
      </div>
    </div>
  )
}
