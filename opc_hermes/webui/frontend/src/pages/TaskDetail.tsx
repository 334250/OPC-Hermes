import { useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

export default function TaskDetail() {
  const { t } = useI18n()
  const [taskId, setTaskId] = useState('')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const lookup = () => {
    if (!taskId.trim()) return
    setLoading(true)
    setError(null)
    api.getTask(taskId.trim())
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">{t('taskDetail')}</h2>

      <div className="flex gap-3 mb-6">
        <input
          className="input flex-1 max-w-md"
          placeholder={t('enterTaskId')}
          value={taskId}
          onChange={e => setTaskId(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && lookup()}
        />
        <button onClick={lookup} className="btn-primary" disabled={loading}>
          {loading ? t('loading') : t('lookup')}
        </button>
      </div>

      {error && <div className="card border-opc-error/50 mb-6"><p className="text-red-400 text-sm">{error}</p></div>}

      {data && (
        <>
          {/* DAG */}
          {data.dag?.nodes?.length > 0 && (
            <div className="card mb-6">
              <h3 className="text-sm font-semibold text-opc-text-2 uppercase tracking-wider mb-4">{t('workflowDag')}</h3>
              <div className="flex flex-wrap gap-4 items-center">
                {data.dag.nodes.map((node: any, i: number) => (
                  <div key={node.id} className="flex items-center gap-2">
                    {i > 0 && <span className="text-opc-text-2 mx-2">→</span>}
                    <div className={`card px-3 py-2 text-sm ${
                      node.status === 'completed' ? 'border-green-500/30' :
                      node.status === 'failed' ? 'border-red-500/30' :
                      'border-opc-border'
                    }`}>
                      <div className="font-medium text-xs">{node.label ?? node.worker_id}</div>
                      <span className={`badge-${node.status === 'completed' ? 'success' : node.status === 'failed' ? 'error' : node.status === 'in_progress' ? 'warning' : 'info'} text-[10px]`}>
                        {node.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Steps */}
          <h3 className="text-sm font-semibold text-opc-text-2 uppercase tracking-wider mb-3">{t('steps')} ({data.steps?.length ?? 0})</h3>
          <div className="space-y-3">
            {data.steps?.map((step: any) => (
              <div key={step.step_index} className="card">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">{t('step')} {step.step_index}: {step.worker_id}</span>
                  <span className={`badge-${step.reports?.[0]?.status === 'completed' ? 'success' : step.reports?.[0]?.status === 'failed' ? 'error' : 'info'} text-xs`}>
                    {step.reports?.[0]?.status ?? 'unknown'}
                  </span>
                </div>
                <p className="text-xs text-opc-text-2 mb-2">{step.prompt?.slice(0, 300)}</p>
                <div className="flex gap-3 text-xs text-opc-text-2">
                  <span>{t('complexity')}: {step.complexity}</span>
                  <span>{t('model')}: {step.model || 'default'}</span>
                  <span>{t('outputFormat')}: {step.expected_output_format}</span>
                </div>
                {step.reports?.map((r: any) => r.output_preview && (
                  <pre key={r.reported_at} className="mt-3 p-3 bg-opc-bg rounded-lg text-xs text-opc-text-2 overflow-auto max-h-40">{r.output_preview}</pre>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
