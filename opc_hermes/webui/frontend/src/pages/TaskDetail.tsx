import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type PipelineTemplateDef } from '../lib/api'
import { useI18n } from '../lib/i18n'

export default function TaskDetail() {
  const { t, lang } = useI18n()
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const isNew = !taskId

  // ── View mode state ──
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ── Creation mode state ──
  const [pipelines, setPipelines] = useState<PipelineTemplateDef[]>([])
  const [selectedPipeline, setSelectedPipeline] = useState('')
  const [userRequest, setUserRequest] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')

  // Load pipelines for creation form
  useEffect(() => {
    if (!isNew) return
    api.listPipelines().then(res => {
      const templates = res.templates ?? []
      setPipelines(templates)
      if (templates.length > 0) setSelectedPipeline(templates[0].id)
    }).catch(() => {})
  }, [isNew])

  // Auto-load task detail
  useEffect(() => {
    if (!taskId) return
    setLoading(true)
    setError(null)
    api.getTask(taskId)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [taskId])

  const handleCreate = useCallback(async () => {
    if (!selectedPipeline || !userRequest.trim()) return
    setCreating(true)
    setCreateError('')
    try {
      const result = await api.executePipeline(selectedPipeline, userRequest.trim())
      navigate(`/tasks/${result.task_id}`)
    } catch (e: any) {
      setCreateError(e.message || 'Execution failed')
    } finally {
      setCreating(false)
    }
  }, [selectedPipeline, userRequest, navigate])

  // ── Creation form ──
  if (isNew) {
    const currentPipeline = pipelines.find(p => p.id === selectedPipeline)

    return (
      <div>
        <h2 className="text-xl font-semibold mb-2">{lang === 'zh' ? '新建任务' : 'New Task'}</h2>
        <p className="text-sm text-opc-text-2 mb-6">
          {lang === 'zh'
            ? '描述你想要完成的任务，选择一个流水线模板来执行。'
            : 'Describe the task you want to accomplish and select a pipeline template to execute.'}
        </p>

        <div className="card mb-4">
          <label className="block mb-4">
            <span className="mb-2 block text-sm font-semibold text-opc-text-2 uppercase tracking-wider">
              {lang === 'zh' ? '流水线模板' : 'Pipeline Template'}
            </span>
            <select
              className="input max-w-md"
              value={selectedPipeline}
              onChange={e => setSelectedPipeline(e.target.value)}
            >
              {pipelines.length === 0 && (
                <option value="">{lang === 'zh' ? '加载中...' : 'Loading...'}</option>
              )}
              {pipelines.map(p => (
                <option key={p.id} value={p.id}>{p.name} ({p.id})</option>
              ))}
            </select>
          </label>

          {currentPipeline && (
            <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-opc-border bg-opc-surface-2 p-3">
                <div className="text-xs text-opc-text-2 mb-1">{lang === 'zh' ? '描述' : 'Description'}</div>
                <div className="text-sm">{currentPipeline.description || '—'}</div>
              </div>
              <div className="rounded-lg border border-opc-border bg-opc-surface-2 p-3">
                <div className="text-xs text-opc-text-2 mb-1">{lang === 'zh' ? '模式 · 步骤数' : 'Mode · Steps'}</div>
                <div className="text-sm">{currentPipeline.mode} · {currentPipeline.steps?.length ?? 0} {lang === 'zh' ? '个步骤' : ' steps'}</div>
              </div>
              {currentPipeline.steps?.length > 0 && (
                <div className="rounded-lg border border-opc-border bg-opc-surface-2 p-3 md:col-span-2">
                  <div className="text-xs text-opc-text-2 mb-2">{lang === 'zh' ? '工作流预览' : 'Workflow Preview'}</div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    {currentPipeline.steps.map((step, i) => (
                      <span key={step.index} className="flex items-center gap-1">
                        {i > 0 && <span className="text-opc-text-2">→</span>}
                        <span className="rounded bg-opc-bg px-2 py-1 font-medium">{step.worker_id}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-opc-text-2 uppercase tracking-wider">
              {lang === 'zh' ? '任务描述' : 'Task Request'}
            </span>
            <textarea
              className="input min-h-[160px] w-full resize-y"
              value={userRequest}
              onChange={e => setUserRequest(e.target.value)}
              placeholder={lang === 'zh'
                ? '用自然语言描述你想完成的任务，例如：分析这份代码的安全性，生成一份报告...'
                : 'Describe your task in natural language, e.g.: Analyze the security of this codebase and generate a report...'}
              disabled={creating}
            />
          </label>

          {createError && (
            <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-400">
              {createError}
            </div>
          )}

          <div className="mt-4 flex items-center gap-3">
            <button
              className="btn-primary"
              onClick={handleCreate}
              disabled={!userRequest.trim() || !selectedPipeline || creating}
            >
              {creating
                ? (lang === 'zh' ? '正在创建任务...' : 'Creating task...')
                : (lang === 'zh' ? '创建并执行任务' : 'Create & Execute Task')}
            </button>
            <span className="text-xs text-opc-text-2">
              {lang === 'zh' ? '将通过 Leader 智能体解析并分派给 Worker 执行' : 'Will be parsed by Leader agent and dispatched to Workers'}
            </span>
          </div>
        </div>
      </div>
    )
  }

  // ── View mode ──
  if (loading) {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-6">{t('taskDetail')}</h2>
        <div className="card animate-pulse"><div className="h-64 bg-opc-surface-2 rounded" /></div>
      </div>
    )
  }

  if (error) {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-6">{t('taskDetail')}</h2>
        <div className="card border-red-500/30 bg-red-500/5 mb-6">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">{t('taskDetail')}</h2>

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
