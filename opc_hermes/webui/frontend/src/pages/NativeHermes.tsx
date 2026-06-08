import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, type HermesCronJob, type HermesEnvVarInfo, type HermesModelOptionProvider, type HermesSessionInfo, type HermesSessionMessage } from '../lib/api'
import { useI18n } from '../lib/i18n'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

function formatTime(value?: number | string | null) {
  if (!value) return '-'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}

function truncate(value: string | null | undefined, max = 120) {
  if (!value) return '-'
  return value.length > max ? `${value.slice(0, max)}...` : value
}

function asText(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-xl font-semibold">{title}</h2>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-opc-text-2">{subtitle}</p>}
      </div>
      {action && <div className="flex flex-wrap items-center gap-2">{action}</div>}
    </div>
  )
}

function LoadingBlock() {
  return <div className="card animate-pulse"><div className="h-96 rounded-lg bg-opc-surface-2" /></div>
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useI18n()
  return (
    <div className="card border-red-500/30 bg-red-500/5">
      <p className="text-sm text-red-400">{t('failedToLoad')}: {message}</p>
      <button className="btn-primary mt-3 text-xs" onClick={onRetry}>{t('retry')}</button>
    </div>
  )
}

function EmptyBlock({ label }: { label: string }) {
  return <div className="py-14 text-center text-sm text-opc-text-2">{label}</div>
}

function StatusBadge({ active, trueLabel = 'Active', falseLabel = 'Inactive' }: { active: boolean; trueLabel?: string; falseLabel?: string }) {
  return <span className={active ? 'badge-success' : 'badge-warning'}>{active ? trueLabel : falseLabel}</span>
}

function MessageBlock({ message }: { message: HermesSessionMessage }) {
  const label = message.tool_name ? `tool: ${message.tool_name}` : message.role
  const tone = message.role === 'assistant' ? 'border-green-500/20 bg-green-500/5' : message.role === 'user' ? 'border-blue-500/20 bg-blue-500/5' : 'border-opc-border bg-opc-bg'
  return (
    <div className={`rounded-lg border p-3 ${tone}`}>
      <div className="mb-2 flex items-center justify-between gap-2 text-xs">
        <span className="font-semibold uppercase tracking-wider text-opc-text-2">{label}</span>
        {message.timestamp && <span className="text-opc-text-2">{formatTime(message.timestamp)}</span>}
      </div>
      {message.content && <div className="whitespace-pre-wrap text-sm leading-6 text-opc-text">{message.content}</div>}
      {message.tool_calls?.length ? (
        <div className="mt-3 space-y-2">
          {message.tool_calls.map((call) => (
            <details key={call.id} className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-2">
              <summary className="cursor-pointer text-xs font-medium text-yellow-400">{call.function.name}</summary>
              <pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs text-opc-text-2">{call.function.arguments}</pre>
            </details>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function HermesSessionsPage() {
  const { lang } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [sessions, setSessions] = useState<HermesSessionInfo[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [messages, setMessages] = useState<HermesSessionMessage[]>([])
  const limit = 30

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      const data = query.trim()
        ? await api.hermesSearchSessions(query.trim(), limit).then((r) => ({
            sessions: r.results.map((x) => ({
              id: x.session_id,
              source: x.source,
              model: x.model,
              title: null,
              started_at: x.session_started ?? 0,
              ended_at: null,
              last_active: x.session_started ?? 0,
              is_active: false,
              message_count: 0,
              tool_call_count: 0,
              input_tokens: 0,
              output_tokens: 0,
              preview: x.snippet,
            })),
            total: r.results.length,
          }))
        : await api.hermesSessions(limit, offset)
      setSessions(data.sessions ?? [])
      setTotal(data.total ?? data.sessions?.length ?? 0)
      setSelected((current) => current ?? data.sessions?.[0]?.id ?? null)
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [offset, query])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!selected) {
      setMessages([])
      return
    }
    api.hermesSessionMessages(selected)
      .then((d) => setMessages(d.messages ?? []))
      .catch(() => setMessages([]))
  }, [selected])

  const deleteSelected = async () => {
    if (!selected || !window.confirm(lang === 'zh' ? '删除这个 Hermes 会话？' : 'Delete this Hermes session?')) return
    await api.hermesDeleteSession(selected)
    setSelected(null)
    load()
  }

  if (state === 'loading') return <LoadingBlock />
  if (state === 'error') return <ErrorBlock message={error} onRetry={load} />

  return (
    <div>
      <PageHeader
        title={lang === 'zh' ? 'Hermes 会话' : 'Hermes Sessions'}
        subtitle={lang === 'zh' ? '浏览原生 Hermes 会话、消息轨迹、搜索结果和 token/工具调用统计。' : 'Browse native Hermes sessions, messages, search results, and usage counters.'}
        action={<button className="btn-secondary text-xs" onClick={load}>{lang === 'zh' ? '刷新' : 'Refresh'}</button>}
      />
      <div className="mb-4 flex flex-col gap-2 md:flex-row">
        <input className="input" value={query} onChange={(e) => { setOffset(0); setQuery(e.target.value) }} placeholder={lang === 'zh' ? '搜索会话内容...' : 'Search session content...'} />
        <button className="btn-secondary whitespace-nowrap text-xs" onClick={() => { setQuery(''); setOffset(0) }}>{lang === 'zh' ? '清空' : 'Clear'}</button>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
        <div className="space-y-3">
          {sessions.length ? sessions.map((session) => (
            <button
              key={session.id}
              className={`card block w-full text-left ${selected === session.id ? 'border-opc-accent/60 bg-opc-accent/5' : ''}`}
              onClick={() => setSelected(session.id)}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{session.title || session.id}</div>
                  <div className="mt-1 text-xs text-opc-text-2">{session.source || 'cli'} · {session.model || '-'}</div>
                </div>
                <StatusBadge active={session.is_active} />
              </div>
              <p className="mt-3 text-xs leading-5 text-opc-text-2">{truncate(session.preview, 180)}</p>
              <div className="mt-3 flex flex-wrap gap-3 text-xs text-opc-text-2">
                <span>{session.message_count} msg</span>
                <span>{session.tool_call_count} tools</span>
                <span>{formatTime(session.last_active || session.started_at)}</span>
              </div>
            </button>
          )) : <EmptyBlock label={lang === 'zh' ? '暂无会话' : 'No sessions'} />}
          {!query && total > limit && (
            <div className="flex items-center justify-between">
              <button className="btn-secondary text-xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>{lang === 'zh' ? '上一页' : 'Prev'}</button>
              <span className="text-xs text-opc-text-2">{offset + 1}-{Math.min(offset + limit, total)} / {total}</span>
              <button className="btn-secondary text-xs" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>{lang === 'zh' ? '下一页' : 'Next'}</button>
            </div>
          )}
        </div>
        <div className="card">
          <div className="mb-4 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{selected || (lang === 'zh' ? '未选择会话' : 'No session selected')}</h3>
            {selected && (
              <div className="flex flex-wrap gap-2">
                <Link className="btn-secondary text-xs" to={`/chat?resume=${encodeURIComponent(selected)}`}>{lang === 'zh' ? '在 Chat 恢复' : 'Resume in Chat'}</Link>
                <button className="btn-danger text-xs" onClick={deleteSelected}>{lang === 'zh' ? '删除' : 'Delete'}</button>
              </div>
            )}
          </div>
          <div className="max-h-[680px] space-y-3 overflow-auto">
            {messages.length ? messages.map((message, index) => <MessageBlock key={index} message={message} />) : <EmptyBlock label={lang === 'zh' ? '暂无消息' : 'No messages'} />}
          </div>
        </div>
      </div>
    </div>
  )
}

function providerModels(providers: HermesModelOptionProvider[], slug: string) {
  return providers.find((p) => p.slug === slug || p.name === slug)?.models ?? []
}

export function HermesModelsPage() {
  const { lang } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [info, setInfo] = useState<any>(null)
  const [providers, setProviders] = useState<HermesModelOptionProvider[]>([])
  const [aux, setAux] = useState<any[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [auxDraft, setAuxDraft] = useState<Record<string, { provider: string; model: string }>>({})
  const [saving, setSaving] = useState('')

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      const [modelInfo, options, auxiliary] = await Promise.all([
        api.hermesModelInfo(),
        api.hermesModelOptions(),
        api.hermesAuxiliaryModels(),
      ])
      const optionProviders = options.providers ?? []
      const currentProvider = modelInfo.provider || options.provider || auxiliary.main?.provider || optionProviders[0]?.slug || ''
      const currentModel = modelInfo.model || options.model || auxiliary.main?.model || ''
      setInfo(modelInfo)
      setProviders(optionProviders)
      setAux(auxiliary.tasks ?? [])
      setProvider(currentProvider)
      setModel(currentModel)
      setAuxDraft(Object.fromEntries((auxiliary.tasks ?? []).map((row) => [row.task, { provider: row.provider, model: row.model }])))
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const saveMain = async () => {
    setSaving('main')
    try {
      await api.hermesSetModel({ scope: 'main', provider, model })
      await load()
    } finally {
      setSaving('')
    }
  }

  const saveAux = async (task: string) => {
    const draft = auxDraft[task]
    if (!draft) return
    setSaving(task)
    try {
      await api.hermesSetModel({ scope: 'auxiliary', provider: draft.provider, model: draft.model, task })
      await load()
    } finally {
      setSaving('')
    }
  }

  const mainModels = providerModels(providers, provider)

  if (state === 'loading') return <LoadingBlock />
  if (state === 'error') return <ErrorBlock message={error} onRetry={load} />

  return (
    <div>
      <PageHeader
        title={lang === 'zh' ? 'Hermes 模型' : 'Hermes Models'}
        subtitle={lang === 'zh' ? '迁入原生模型信息、Provider 模型选择和辅助任务模型分配。保存后影响新会话。' : 'Native model metadata, provider choices, and auxiliary task assignments. Saves affect new sessions.'}
        action={<button className="btn-secondary text-xs" onClick={load}>{lang === 'zh' ? '刷新' : 'Refresh'}</button>}
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="card xl:col-span-1">
          <h3 className="mb-4 text-sm font-semibold">{lang === 'zh' ? '当前主模型' : 'Current Main Model'}</h3>
          <div className="space-y-3 text-sm">
            <InfoRow label="Provider" value={info?.provider || '-'} />
            <InfoRow label="Model" value={info?.model || '-'} />
            <InfoRow label="Context" value={String(info?.effective_context_length || 0)} />
            <InfoRow label="Tools" value={info?.capabilities?.supports_tools ? 'yes' : 'no'} />
            <InfoRow label="Vision" value={info?.capabilities?.supports_vision ? 'yes' : 'no'} />
          </div>
        </div>
        <div className="card xl:col-span-2">
          <h3 className="mb-4 text-sm font-semibold">{lang === 'zh' ? '设置主模型' : 'Set Main Model'}</h3>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <select className="input" value={provider} onChange={(e) => { setProvider(e.target.value); setModel(providerModels(providers, e.target.value)[0] ?? '') }}>
              {providers.map((p) => <option key={p.slug || p.name} value={p.slug || p.name}>{p.name || p.slug} {p.total_models ? `(${p.total_models})` : ''}</option>)}
            </select>
            {mainModels.length ? (
              <select className="input" value={model} onChange={(e) => setModel(e.target.value)}>
                {mainModels.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            ) : (
              <input className="input" value={model} onChange={(e) => setModel(e.target.value)} placeholder="provider/model" />
            )}
          </div>
          <button className="btn-primary mt-4 text-xs" disabled={!provider || !model || saving === 'main'} onClick={saveMain}>{lang === 'zh' ? '保存主模型' : 'Save Main Model'}</button>
        </div>
      </div>
      <div className="card mt-4">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold">{lang === 'zh' ? '辅助模型' : 'Auxiliary Models'}</h3>
          <button className="btn-secondary text-xs" disabled={saving === '__reset__'} onClick={async () => { setSaving('__reset__'); await api.hermesSetModel({ scope: 'auxiliary', provider: 'auto', model: '', task: '__reset__' }); setSaving(''); load() }}>{lang === 'zh' ? '全部重置为 auto' : 'Reset All to Auto'}</button>
        </div>
        <div className="overflow-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-opc-text-2">
              <tr><th className="py-2">Task</th><th>Provider</th><th>Model</th><th className="w-24"></th></tr>
            </thead>
            <tbody className="divide-y divide-opc-border">
              {aux.map((row) => {
                const draft = auxDraft[row.task] ?? { provider: row.provider, model: row.model }
                const models = providerModels(providers, draft.provider)
                return (
                  <tr key={row.task}>
                    <td className="py-3 font-medium">{row.task}</td>
                    <td className="py-3 pr-3">
                      <select className="input" value={draft.provider} onChange={(e) => setAuxDraft((prev) => ({ ...prev, [row.task]: { provider: e.target.value, model: e.target.value === 'auto' ? '' : providerModels(providers, e.target.value)[0] ?? draft.model } }))}>
                        <option value="auto">auto</option>
                        {providers.map((p) => <option key={p.slug || p.name} value={p.slug || p.name}>{p.name || p.slug}</option>)}
                      </select>
                    </td>
                    <td className="py-3 pr-3">
                      {models.length ? (
                        <select className="input" value={draft.model} onChange={(e) => setAuxDraft((prev) => ({ ...prev, [row.task]: { ...draft, model: e.target.value } }))}>
                          <option value="">default</option>
                          {models.map((m) => <option key={m} value={m}>{m}</option>)}
                        </select>
                      ) : (
                        <input className="input" value={draft.model} onChange={(e) => setAuxDraft((prev) => ({ ...prev, [row.task]: { ...draft, model: e.target.value } }))} placeholder="default" />
                      )}
                    </td>
                    <td className="py-3 text-right"><button className="btn-secondary text-xs" disabled={saving === row.task} onClick={() => saveAux(row.task)}>{lang === 'zh' ? '保存' : 'Save'}</button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-4 border-b border-opc-border py-2"><span className="text-opc-text-2">{label}</span><span className="text-right font-mono text-xs">{value}</span></div>
}

export function HermesConfigPage() {
  const { lang } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [config, setConfig] = useState<Record<string, any>>({})
  const [schema, setSchema] = useState<{ fields: Record<string, any>; category_order: string[] }>({ fields: {}, category_order: [] })
  const [selectedCategory, setSelectedCategory] = useState('general')
  const [edited, setEdited] = useState('')
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      const [cfg, sch] = await Promise.all([api.hermesConfig(), api.hermesConfigSchema()])
      setConfig(cfg)
      setSchema(sch)
      setEdited(JSON.stringify(cfg, null, 2))
      setSelectedCategory(sch.category_order?.[0] ?? 'general')
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const categories = useMemo(() => {
    const set = new Set(Object.values(schema.fields).map((field: any) => field.category || 'general'))
    return [...(schema.category_order ?? []), ...Array.from(set).sort()].filter((value, index, arr) => value && arr.indexOf(value) === index)
  }, [schema])

  const visibleFields = useMemo(() => Object.entries(schema.fields).filter(([, field]: any) => (field.category || 'general') === selectedCategory), [schema, selectedCategory])

  const save = async () => {
    try {
      const parsed = JSON.parse(edited)
      await api.hermesSaveConfig(parsed)
      setConfig(parsed)
      setMessage(lang === 'zh' ? '已保存' : 'Saved')
      setTimeout(() => setMessage(''), 2000)
    } catch (e: any) {
      setMessage(`${lang === 'zh' ? '保存失败' : 'Save failed'}: ${e.message}`)
    }
  }

  if (state === 'loading') return <LoadingBlock />
  if (state === 'error') return <ErrorBlock message={error} onRetry={load} />

  return (
    <div>
      <PageHeader
        title={lang === 'zh' ? 'Hermes 配置' : 'Hermes Config'}
        subtitle={lang === 'zh' ? '读取原生 Hermes 配置、默认 schema 分类，并以 JSON 方式保存到 Hermes 配置。' : 'Native Hermes config with schema categories and JSON save.'}
        action={<><span className={`text-xs ${message.includes('失败') || message.includes('failed') ? 'text-red-400' : 'text-green-400'}`}>{message}</span><button className="btn-primary text-xs" onClick={save}>{lang === 'zh' ? '保存' : 'Save'}</button></>}
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="card">
          <h3 className="mb-3 text-sm font-semibold">{lang === 'zh' ? 'Schema 分类' : 'Schema Categories'}</h3>
          <div className="space-y-1">
            {categories.map((cat) => (
              <button key={cat} className={`w-full rounded-lg px-3 py-2 text-left text-sm ${selectedCategory === cat ? 'bg-opc-accent/10 text-opc-accent' : 'text-opc-text-2 hover:bg-opc-surface-2 hover:text-opc-text'}`} onClick={() => setSelectedCategory(cat)}>
                {cat}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-4">
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold">{selectedCategory}</h3>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {visibleFields.map(([key, field]: any) => (
                <div key={key} className="rounded-lg border border-opc-border bg-opc-bg p-3">
                  <div className="font-mono text-xs text-opc-accent">{key}</div>
                  <div className="mt-1 text-xs text-opc-text-2">{field.description || field.type}</div>
                  <div className="mt-2 truncate font-mono text-xs">{JSON.stringify(config[key] ?? null)}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold">{lang === 'zh' ? '完整 JSON' : 'Full JSON'}</h3>
            <textarea className="h-[520px] w-full resize-none rounded-lg border border-opc-border bg-opc-bg p-4 font-mono text-sm text-opc-text focus:border-opc-accent/50 focus:outline-none" value={edited} onChange={(e) => setEdited(e.target.value)} spellCheck={false} />
          </div>
        </div>
      </div>
    </div>
  )
}

export function HermesKeysPage() {
  const { lang } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [env, setEnv] = useState<Record<string, HermesEnvVarInfo>>({})
  const [oauth, setOauth] = useState<any[]>([])
  const [key, setKey] = useState('')
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      const [vars, providers] = await Promise.all([api.hermesEnv(), api.hermesOAuthProviders().catch(() => ({ providers: [] }))])
      setEnv(vars)
      setOauth(providers.providers ?? [])
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const groups = useMemo(() => {
    const result: Record<string, Array<[string, HermesEnvVarInfo]>> = {}
    Object.entries(env).forEach((entry) => {
      const cat = entry[1].category || 'general'
      result[cat] = [...(result[cat] ?? []), entry]
    })
    return result
  }, [env])

  const setVar = async () => {
    if (!key.trim()) return
    setBusy('set')
    try {
      await api.hermesSetEnv(key.trim(), value)
      setValue('')
      await load()
    } finally {
      setBusy('')
    }
  }

  const deleteVar = async (name: string) => {
    if (!window.confirm(lang === 'zh' ? `删除 ${name}？` : `Delete ${name}?`)) return
    setBusy(name)
    try {
      await api.hermesDeleteEnv(name)
      await load()
    } finally {
      setBusy('')
    }
  }

  if (state === 'loading') return <LoadingBlock />
  if (state === 'error') return <ErrorBlock message={error} onRetry={load} />

  return (
    <div>
      <PageHeader
        title={lang === 'zh' ? 'Hermes Keys' : 'Hermes Keys'}
        subtitle={lang === 'zh' ? '查看原生 Hermes .env Key 状态和 OAuth Provider 连接状态，可写入或删除 Key。' : 'Inspect native Hermes .env keys and OAuth provider status. Set or delete keys.'}
        action={<button className="btn-secondary text-xs" onClick={load}>{lang === 'zh' ? '刷新' : 'Refresh'}</button>}
      />
      <div className="card mb-4">
        <h3 className="mb-3 text-sm font-semibold">{lang === 'zh' ? '设置 Key' : 'Set Key'}</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[260px_minmax(0,1fr)_auto]">
          <input className="input" value={key} onChange={(e) => setKey(e.target.value)} placeholder="OPENAI_API_KEY" />
          <input className="input" type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder={lang === 'zh' ? '新值' : 'New value'} />
          <button className="btn-primary text-xs" disabled={busy === 'set'} onClick={setVar}>{lang === 'zh' ? '保存' : 'Save'}</button>
        </div>
      </div>
      <div className="card mb-4">
        <h3 className="mb-3 text-sm font-semibold">OAuth</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {oauth.map((provider) => (
            <div key={provider.id} className="rounded-lg border border-opc-border bg-opc-bg p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="font-medium">{provider.name}</div>
                <StatusBadge active={!!provider.status?.logged_in} trueLabel={lang === 'zh' ? '已连接' : 'Connected'} falseLabel={lang === 'zh' ? '未连接' : 'Missing'} />
              </div>
              <div className="mt-2 text-xs text-opc-text-2">{provider.status?.source_label || provider.cli_command}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-4">
        {Object.entries(groups).map(([category, vars]) => (
          <div key={category} className="card">
            <h3 className="mb-3 text-sm font-semibold">{category}</h3>
            <div className="divide-y divide-opc-border">
              {vars.map(([name, info]) => (
                <div key={name} className="grid grid-cols-1 gap-3 py-3 md:grid-cols-[240px_minmax(0,1fr)_170px_auto] md:items-center">
                  <div className="font-mono text-sm">{name}</div>
                  <div className="text-xs text-opc-text-2">{info.description}</div>
                  <div className="font-mono text-xs">{info.is_set ? info.redacted_value || 'set' : '-'}</div>
                  <button className="btn-danger text-xs" disabled={!info.is_set || busy === name} onClick={() => deleteVar(name)}>{lang === 'zh' ? '删除' : 'Delete'}</button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function HermesLogsPage() {
  const { lang } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [lines, setLines] = useState<string[]>([])
  const [file, setFile] = useState('')
  const [lineCount, setLineCount] = useState(300)
  const [level, setLevel] = useState('ALL')
  const [component, setComponent] = useState('all')

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      const data = await api.hermesLogs({ lines: lineCount, level, component })
      setLines(data.lines ?? [])
      setFile(data.file)
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [lineCount, level, component])

  useEffect(() => { load() }, [load])

  return (
    <div>
      <PageHeader
        title={lang === 'zh' ? 'Hermes 日志' : 'Hermes Logs'}
        subtitle={file || (lang === 'zh' ? '查看原生日志尾部，支持按行数、等级、组件过滤。' : 'Tail native logs with line, level, and component filters.')}
        action={<button className="btn-secondary text-xs" onClick={load}>{lang === 'zh' ? '刷新' : 'Refresh'}</button>}
      />
      <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-[140px_160px_180px_auto]">
        <input className="input" type="number" min={20} max={2000} value={lineCount} onChange={(e) => setLineCount(Number(e.target.value) || 300)} />
        <select className="input" value={level} onChange={(e) => setLevel(e.target.value)}>
          {['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR'].map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <input className="input" value={component} onChange={(e) => setComponent(e.target.value || 'all')} placeholder="component" />
      </div>
      {state === 'error' ? <ErrorBlock message={error} onRetry={load} /> : (
        <div className="card">
          {state === 'loading' ? <div className="h-96 animate-pulse rounded-lg bg-opc-surface-2" /> : (
            <pre className="max-h-[720px] overflow-auto rounded-lg bg-opc-bg p-4 text-xs leading-5 text-opc-text-2">{lines.join('\n') || (lang === 'zh' ? '暂无日志' : 'No logs')}</pre>
          )}
        </div>
      )}
    </div>
  )
}

function jobTitle(job: HermesCronJob) {
  return asText(job.name).trim() || truncate(asText(job.prompt) || asText(job.script), 80)
}

function jobProfile(job: HermesCronJob) {
  return asText(job.profile) || asText(job.profile_name) || 'default'
}

function jobSchedule(job: HermesCronJob) {
  return asText(job.schedule_display) || asText(job.schedule?.display) || asText(job.schedule?.expr) || '-'
}

export function HermesCronPage() {
  const { lang } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [jobs, setJobs] = useState<HermesCronJob[]>([])
  const [profile, setProfile] = useState('all')
  const [busy, setBusy] = useState('')
  const [form, setForm] = useState({ name: '', schedule: '', prompt: '', deliver: 'local' })

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      setJobs(await api.hermesCronJobs(profile))
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [profile])

  useEffect(() => { load() }, [load])

  const runJobAction = async (key: string, fn: () => Promise<any>) => {
    setBusy(key)
    try {
      await fn()
      await load()
    } finally {
      setBusy('')
    }
  }

  const create = async () => {
    if (!form.prompt.trim() || !form.schedule.trim()) return
    await runJobAction('create', () => api.hermesCreateCronJob({ prompt: form.prompt.trim(), schedule: form.schedule.trim(), name: form.name.trim() || undefined, deliver: form.deliver }, profile === 'all' ? 'default' : profile))
    setForm({ name: '', schedule: '', prompt: '', deliver: 'local' })
  }

  if (state === 'error') return <ErrorBlock message={error} onRetry={load} />

  return (
    <div>
      <PageHeader
        title={lang === 'zh' ? 'Hermes Cron' : 'Hermes Cron'}
        subtitle={lang === 'zh' ? '迁入原生定时任务列表、创建、触发、暂停、恢复和删除。' : 'Native scheduled jobs: list, create, trigger, pause, resume, and delete.'}
        action={<><input className="input w-36" value={profile} onChange={(e) => setProfile(e.target.value || 'all')} /><button className="btn-secondary text-xs" onClick={load}>{lang === 'zh' ? '刷新' : 'Refresh'}</button></>}
      />
      <div className="card mb-4">
        <h3 className="mb-3 text-sm font-semibold">{lang === 'zh' ? '新建任务' : 'New Job'}</h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={lang === 'zh' ? '名称（可选）' : 'Name (optional)'} />
          <input className="input" value={form.schedule} onChange={(e) => setForm({ ...form, schedule: e.target.value })} placeholder="*/15 * * * *" />
          <input className="input" value={form.deliver} onChange={(e) => setForm({ ...form, deliver: e.target.value })} placeholder="local" />
          <button className="btn-primary text-xs" disabled={busy === 'create'} onClick={create}>{lang === 'zh' ? '创建' : 'Create'}</button>
        </div>
        <textarea className="input mt-3 h-24 resize-none" value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} placeholder={lang === 'zh' ? '任务 Prompt' : 'Job prompt'} />
      </div>
      {state === 'loading' ? <LoadingBlock /> : (
        <div className="space-y-3">
          {jobs.length ? jobs.map((job) => {
            const profileName = jobProfile(job)
            const paused = (job.state || '').toLowerCase() === 'paused' || job.enabled === false
            return (
              <div key={`${profileName}:${job.id}`} className="card">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="font-semibold">{jobTitle(job)}</div>
                    <p className="mt-1 text-sm text-opc-text-2">{truncate(job.prompt || job.script, 220)}</p>
                    <div className="mt-3 flex flex-wrap gap-3 text-xs text-opc-text-2">
                      <span>{profileName}</span>
                      <span>{jobSchedule(job)}</span>
                      <span>next: {formatTime(job.next_run_at)}</span>
                      <span>last: {formatTime(job.last_run_at)}</span>
                    </div>
                    {job.last_error && <div className="mt-2 text-xs text-red-400">{job.last_error}</div>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge active={!paused} trueLabel={job.state || 'scheduled'} falseLabel={job.state || 'paused'} />
                    <button className="btn-secondary text-xs" disabled={busy === `trigger-${job.id}`} onClick={() => runJobAction(`trigger-${job.id}`, () => api.hermesTriggerCronJob(job.id, profileName))}>{lang === 'zh' ? '触发' : 'Trigger'}</button>
                    <button className="btn-secondary text-xs" disabled={busy === `pause-${job.id}`} onClick={() => runJobAction(`pause-${job.id}`, () => paused ? api.hermesResumeCronJob(job.id, profileName) : api.hermesPauseCronJob(job.id, profileName))}>{paused ? (lang === 'zh' ? '恢复' : 'Resume') : (lang === 'zh' ? '暂停' : 'Pause')}</button>
                    <button className="btn-danger text-xs" disabled={busy === `delete-${job.id}`} onClick={() => window.confirm(lang === 'zh' ? '删除这个 Cron 任务？' : 'Delete this cron job?') && runJobAction(`delete-${job.id}`, () => api.hermesDeleteCronJob(job.id, profileName))}>{lang === 'zh' ? '删除' : 'Delete'}</button>
                  </div>
                </div>
              </div>
            )
          }) : <EmptyBlock label={lang === 'zh' ? '暂无 Cron 任务' : 'No cron jobs'} />}
        </div>
      )}
    </div>
  )
}

export function HermesSkillsPage() {
  const { lang } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [skills, setSkills] = useState<any[]>([])
  const [toolsets, setToolsets] = useState<any[]>([])
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      const [skillRows, toolsetRows] = await Promise.all([api.hermesSkills(), api.hermesToolsets()])
      setSkills(skillRows)
      setToolsets(toolsetRows)
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const toggle = async (name: string, enabled: boolean) => {
    setBusy(name)
    try {
      await api.hermesToggleSkill(name, enabled)
      await load()
    } finally {
      setBusy('')
    }
  }

  if (state === 'loading') return <LoadingBlock />
  if (state === 'error') return <ErrorBlock message={error} onRetry={load} />

  return (
    <div>
      <PageHeader
        title={lang === 'zh' ? 'Hermes Skills' : 'Hermes Skills'}
        subtitle={lang === 'zh' ? '迁入原生技能列表、分类、启用开关，以及 Toolset 配置状态。' : 'Native skills with categories, enable toggles, and toolset configuration state.'}
        action={<button className="btn-secondary text-xs" onClick={load}>{lang === 'zh' ? '刷新' : 'Refresh'}</button>}
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {skills.map((skill) => (
            <div key={skill.name} className="card">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold">{skill.name}</div>
                  <div className="mt-1 text-xs text-opc-text-2">{skill.category}</div>
                </div>
                <StatusBadge active={skill.enabled} trueLabel={lang === 'zh' ? '启用' : 'Enabled'} falseLabel={lang === 'zh' ? '停用' : 'Disabled'} />
              </div>
              <p className="mt-3 text-sm leading-6 text-opc-text-2">{skill.description || '-'}</p>
              <button className="btn-secondary mt-4 text-xs" disabled={busy === skill.name} onClick={() => toggle(skill.name, !skill.enabled)}>{skill.enabled ? (lang === 'zh' ? '禁用' : 'Disable') : (lang === 'zh' ? '启用' : 'Enable')}</button>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 className="mb-3 text-sm font-semibold">Toolsets</h3>
          <div className="space-y-3">
            {toolsets.map((toolset) => (
              <div key={toolset.name} className="rounded-lg border border-opc-border bg-opc-bg p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium">{toolset.label || toolset.name}</div>
                    <div className="mt-1 text-xs text-opc-text-2">{toolset.tools?.length ?? 0} tools</div>
                  </div>
                  <StatusBadge active={toolset.enabled && toolset.configured} trueLabel="ready" falseLabel={toolset.enabled ? 'needs config' : 'disabled'} />
                </div>
                <p className="mt-2 text-xs text-opc-text-2">{toolset.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export function HermesPluginsPage() {
  const { lang } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [plugins, setPlugins] = useState<any[]>([])
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      setPlugins(await api.hermesPlugins())
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const rescan = async () => {
    setBusy('rescan')
    try {
      await api.hermesRescanPlugins()
      await load()
    } finally {
      setBusy('')
    }
  }

  const setHidden = async (name: string, hidden: boolean) => {
    setBusy(name)
    try {
      await api.hermesSetPluginVisibility(name, hidden)
      await load()
    } finally {
      setBusy('')
    }
  }

  if (state === 'loading') return <LoadingBlock />
  if (state === 'error') return <ErrorBlock message={error} onRetry={load} />

  return (
    <div>
      <PageHeader
        title={lang === 'zh' ? 'Hermes Plugins' : 'Hermes Plugins'}
        subtitle={lang === 'zh' ? '迁入 Dashboard 插件注册表、入口、API 状态、重新扫描和显隐控制。' : 'Native dashboard plugin registry, entrypoints, API status, rescan, and visibility controls.'}
        action={<button className="btn-secondary text-xs" disabled={busy === 'rescan'} onClick={rescan}>{lang === 'zh' ? '重新扫描' : 'Rescan'}</button>}
      />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {plugins.length ? plugins.map((plugin) => (
          <div key={plugin.name} className="card">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate font-semibold">{plugin.label || plugin.name}</div>
                <div className="mt-1 font-mono text-xs text-opc-text-2">{plugin.name}</div>
              </div>
              <StatusBadge active={!plugin.tab?.hidden} trueLabel={lang === 'zh' ? '显示' : 'Visible'} falseLabel={lang === 'zh' ? '隐藏' : 'Hidden'} />
            </div>
            <p className="mt-3 text-sm leading-6 text-opc-text-2">{plugin.description || '-'}</p>
            <div className="mt-3 space-y-1 text-xs text-opc-text-2">
              <div>version: {plugin.version || '-'}</div>
              <div>tab: {plugin.tab?.path || '-'}</div>
              <div>entry: {plugin.entry || '-'}</div>
              <div>api: {plugin.has_api ? 'yes' : 'no'}</div>
              <div>source: {plugin.source || '-'}</div>
            </div>
            <button className="btn-secondary mt-4 text-xs" disabled={busy === plugin.name} onClick={() => setHidden(plugin.name, !plugin.tab?.hidden)}>{plugin.tab?.hidden ? (lang === 'zh' ? '显示' : 'Show') : (lang === 'zh' ? '隐藏' : 'Hide')}</button>
          </div>
        )) : <EmptyBlock label={lang === 'zh' ? '暂无插件' : 'No plugins'} />}
      </div>
    </div>
  )
}
