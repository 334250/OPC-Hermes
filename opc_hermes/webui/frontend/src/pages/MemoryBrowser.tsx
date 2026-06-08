import { useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

const partitions = [
  { key: 'project', labelKey: 'projectMemory' },
  { key: 'eval', labelKey: 'evalMemory' },
  { key: 'kb', labelKey: 'knowledgeBase' },
]

export default function MemoryBrowser() {
  const { t } = useI18n()
  const [partition, setPartition] = useState('eval')
  const [taskId, setTaskId] = useState('')
  const [workerId, setWorkerId] = useState('')
  const [searchQ, setSearchQ] = useState('')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const browse = () => {
    setLoading(true)
    if (partition === 'kb') {
      api.searchKnowledge(searchQ || '')
        .then(setData)
        .finally(() => setLoading(false))
    } else {
      api.browseMemory(partition, taskId || undefined, workerId || undefined)
        .then(setData)
        .finally(() => setLoading(false))
    }
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">{t('memory')}</h2>

      {/* Partition tabs */}
      <div className="flex gap-1 mb-4">
        {partitions.map(p => (
          <button
            key={p.key}
            onClick={() => { setPartition(p.key); setData(null) }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              partition === p.key ? 'bg-opc-accent text-white' : 'bg-opc-surface-2 text-opc-text-2 hover:text-opc-text'
            }`}
          >
            {t(p.labelKey)}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {partition === 'project' && (
          <input className="input max-w-xs" placeholder="Task ID" value={taskId} onChange={e => setTaskId(e.target.value)} />
        )}
        {partition === 'eval' && (
          <input className="input max-w-xs" placeholder={t('workerIdOptional')} value={workerId} onChange={e => setWorkerId(e.target.value)} />
        )}
        {partition === 'kb' && (
          <input className="input flex-1 max-w-sm" placeholder={t('searchKnowledge')} value={searchQ} onChange={e => setSearchQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && browse()} />
        )}
        <button onClick={browse} className="btn-primary" disabled={loading}>{t('browse')}</button>
      </div>

      {/* Results */}
      {loading && <div className="card animate-pulse"><div className="h-32 bg-opc-surface-2 rounded" /></div>}

      {data && partition === 'eval' && (
        <div className="space-y-2">
          {data.evaluations?.map((e: any) => (
            <div key={e.task_id + e.worker_id} className="card flex items-center justify-between">
              <div>
                <div className="text-sm">{e.worker_id}</div>
                <div className="text-xs text-opc-text-2">{e.task_id} · {e.evaluated_at?.slice(0, 10)}</div>
              </div>
              <div className="flex gap-2">
                {Object.entries(e.scores || {}).map(([k, v]) => (
                  <span key={k} className={`badge-${(v as number) >= 0.7 ? 'success' : (v as number) >= 0.5 ? 'warning' : 'error'} text-xs`}>
                    {k}: {((v as number) * 100).toFixed(0)}%
                  </span>
                ))}
              </div>
            </div>
          ))}
          {!data.evaluations?.length && <EmptyState message={t('noEvaluationsFound')} />}
        </div>
      )}

      {data && partition === 'project' && (
        <div>
          {data.protocols?.map((p: any) => (
            <div key={p.worker_id} className="card mb-2">
              <div className="text-sm font-medium">{p.worker_id} (Step {p.step_index})</div>
              <div className="text-xs text-opc-text-2 mt-1">{p.prompt?.slice(0, 200)}</div>
            </div>
          ))}
          {!data.protocols?.length && !data.reports?.length && <EmptyState message={t('noProjectData')} />}
        </div>
      )}

      {data && partition === 'kb' && (
        <div className="space-y-2">
          {data.results?.map((r: any) => (
            <div key={r.id} className="card">
              <div className="text-sm font-medium">{r.title}</div>
              <div className="text-xs text-opc-text-2 mt-1">{r.content?.slice(0, 300)}</div>
            </div>
          ))}
          {!data.results?.length && <EmptyState message={t('noKnowledgeEntries')} />}
        </div>
      )}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return <div className="py-16 text-center text-opc-text-2 text-sm">{message}</div>
}
