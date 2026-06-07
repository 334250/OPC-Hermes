import { useState, useEffect } from 'react'
import { api } from '../lib/api'

export default function Dashboard() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.dashboard().then(setData).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [])

  if (loading) return <DashboardSkeleton />
  if (error) return <ErrorCard message={error} />

  const stats = data?.stats ?? {}

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Dashboard</h2>

      {/* Stat Cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <StatCard label="Active Tasks" value={stats.active_tasks ?? 0} />
        <StatCard label="Total Workers" value={stats.total_workers ?? 0} />
        <StatCard label="Avg Quality" value={stats.avg_quality ? `${(stats.avg_quality * 100).toFixed(0)}%` : '—'} />
        <StatCard label="Pending Proposals" value={stats.pending_proposals ?? 0} />
        <StatCard label="Recent Evaluations" value={stats.recent_evaluations ?? 0} />
      </div>

      {/* Quality Trend */}
      <div className="card mb-6">
        <h3 className="text-sm font-semibold text-opc-text-2 uppercase tracking-wider mb-4">Quality Trend (30 days)</h3>
        {data?.quality_trend?.length ? (
          <div className="h-48 flex items-end gap-1">
            {data.quality_trend.slice(-30).map((e: any, i: number) => {
              const avg = Object.values(e.scores || {}).length
                ? (Object.values(e.scores) as number[]).reduce((a: number, b: number) => a + b, 0) / Object.values(e.scores).length
                : 0.5
              return (
                <div
                  key={i}
                  className="flex-1 bg-opc-accent/30 hover:bg-opc-accent/60 rounded-t transition-colors"
                  style={{ height: `${avg * 100}%` }}
                  title={`${e.worker_id}: ${(avg * 100).toFixed(0)}%`}
                />
              )
            })}
          </div>
        ) : (
          <EmptyState message="No evaluation data yet" />
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

function ErrorCard({ message }: { message: string }) {
  return (
    <div className="card border-opc-error/50 bg-opc-error/5">
      <p className="text-red-400 text-sm">Failed to load: {message}</p>
      <button onClick={() => window.location.reload()} className="btn-primary mt-3 text-xs">Retry</button>
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div>
      <div className="h-7 w-40 bg-opc-surface-2 rounded mb-6 animate-pulse" />
      <div className="grid grid-cols-4 gap-4 mb-8">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="card animate-pulse">
            <div className="h-8 w-16 bg-opc-surface-2 rounded mb-2" />
            <div className="h-3 w-24 bg-opc-surface-2 rounded opacity-50" />
          </div>
        ))}
      </div>
      <div className="card animate-pulse">
        <div className="h-4 w-40 bg-opc-surface-2 rounded mb-4 opacity-50" />
        <div className="h-48 bg-opc-surface-2 rounded opacity-20" />
      </div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return <div className="py-16 text-center text-opc-text-2 text-sm">{message}</div>
}
