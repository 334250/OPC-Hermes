import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, type HermesCronJob, type HermesEnvVarInfo, type HermesProfileInfo, type HermesSessionInfo, type HermesSessionMessage, type ModelDef, type ModelProviderInfo } from '../lib/api'
import { useI18n } from '../lib/i18n'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

function tierLabel(lang: string, tier: string) {
  const labels: Record<string, Record<string, string>> = {
    zh: { budget: '预算', standard: '标准', premium: '高级' },
    en: { budget: 'Budget', standard: 'Standard', premium: 'Premium' },
  }
  return labels[lang]?.[tier] || tier
}

function envNameFromRef(value?: string | null) {
  const raw = (value || '').trim()
  if (!raw || raw === 'null') return ''
  if (raw.startsWith('${') && raw.endsWith('}')) return raw.slice(2, -1).trim()
  if (raw.startsWith('$')) return raw.slice(1).trim()
  return raw
}

function apiKeyRefFromEnv(value: string) {
  const env = envNameFromRef(value)
  return env ? '${' + env + '}' : ''
}

function defaultApiKeyEnv(providerId: string) {
  const cleaned = (providerId || 'custom').toUpperCase().replace(/[-.]/g, '_')
  return `${cleaned}_API_KEY`
}

function complexityLabel(t: (key: string) => string, value: string) {
  const labels: Record<string, string> = {
    SIMPLE: 'modelComplexitySimple',
    MEDIUM: 'modelComplexityMedium',
    COMPLEX: 'modelComplexityComplex',
  }
  return t(labels[value] || value)
}

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

export function HermesModelsPage() {
  const { lang, t } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [models, setModels] = useState<ModelDef[]>([])
  const [providers, setProviders] = useState<ModelProviderInfo[]>([])
  const [catalog, setCatalog] = useState<any[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [keyEditingId, setKeyEditingId] = useState<string | null>(null)
  const [keyEnv, setKeyEnv] = useState('')
  const [keyValue, setKeyValue] = useState('')

  // Form state
  const [fId, setFId] = useState('')
  const [fCustomModelId, setFCustomModelId] = useState(false)
  const [fDisplayName, setFDisplayName] = useState('')
  const [fProvider, setFProvider] = useState('')
  const [fTier, setFTier] = useState('standard')
  const [fContextLength, setFContextLength] = useState(128000)
  const [fApiBase, setFApiBase] = useState('')
  const [fApiKeyRef, setFApiKeyRef] = useState('')
  const [fApiKeyValue, setFApiKeyValue] = useState('')
  const [fActive, setFActive] = useState(true)
  const [fDescription, setFDescription] = useState('')
  const [fVision, setFVision] = useState(false)
  const [fTools, setFTools] = useState(true)
  const [fImageGen, setFImageGen] = useState(false)
  const [fAudioStt, setFAudioStt] = useState(false)
  const [fSimple, setFSimple] = useState(true)
  const [fMedium, setFMedium] = useState(true)
  const [fComplex, setFComplex] = useState(false)

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      const [modelsRes, providersRes] = await Promise.all([
        api.listModels(),
        api.listModelProviders(),
      ])
      setModels(modelsRes.models ?? [])
      setProviders(providersRes.providers ?? [])
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Lazy-load catalog only when needed (for add/edit dropdowns)
  const loadCatalog = useCallback(async () => {
    if (catalog.length > 0 || catalogLoading) return
    setCatalogLoading(true)
    try {
      const res = await fetch('/api/hermes/opc-model-catalog').then(r => r.json())
      setCatalog(res.providers ?? [])
    } catch {
      // dropdowns will fall back to providers list
    } finally {
      setCatalogLoading(false)
    }
  }, [catalog.length, catalogLoading])

  const resetForm = () => {
    setFId('')
    setFCustomModelId(false)
    setFDisplayName('')
    setFProvider('')
    setFTier('standard')
    setFContextLength(128000)
    setFApiBase('')
    setFApiKeyRef('')
    setFApiKeyValue('')
    setFActive(true)
    setFDescription('')
    setFVision(false)
    setFTools(true)
    setFImageGen(false)
    setFAudioStt(false)
    setFSimple(true)
    setFMedium(true)
    setFComplex(false)
  }

  const startAdd = () => {
    resetForm()
    setAdding(true)
    setEditingId(null)
    setKeyEditingId(null)
  }

  const startEdit = (m: ModelDef) => {
    setFId(m.id)
    setFCustomModelId(false)
    setFDisplayName(m.display_name)
    setFProvider(m.provider)
    setFTier(m.tier)
    setFContextLength(m.context_length)
    setFApiBase(m.api_base || '')
    setFApiKeyRef(m.api_key_ref || '')
    setFApiKeyValue('')
    setFActive(m.active)
    setFDescription(m.description)
    setFVision(m.capabilities?.vision || false)
    setFTools(m.capabilities?.tool_calling ?? true)
    setFImageGen(m.capabilities?.image_gen || false)
    setFAudioStt(m.capabilities?.audio_stt || false)
    setFSimple(m.suitable_complexity?.includes('SIMPLE') ?? true)
    setFMedium(m.suitable_complexity?.includes('MEDIUM') ?? true)
    setFComplex(m.suitable_complexity?.includes('COMPLEX') || false)
    setEditingId(m.id)
    setAdding(false)
    setKeyEditingId(null)
  }

  const cancelForm = () => {
    setAdding(false)
    setEditingId(null)
  }

  const buildPayload = () => {
    const complexity: string[] = []
    if (fSimple) complexity.push('SIMPLE')
    if (fMedium) complexity.push('MEDIUM')
    if (fComplex) complexity.push('COMPLEX')
    return {
      id: fId.trim(),
      display_name: fDisplayName.trim() || fId.trim(),
      provider: fProvider.trim(),
      tier: fTier,
      context_length: fContextLength,
      capabilities: {
        vision: fVision,
        tool_calling: fTools,
        image_gen: fImageGen,
        audio_stt: fAudioStt,
      },
      suitable_complexity: complexity,
      api_base: fApiBase.trim() || null,
      api_key_ref: apiKeyRefFromEnv(fApiKeyRef.trim()) || null,
      active: fActive,
      description: fDescription.trim(),
    }
  }

  const handleSave = async () => {
    if (!fId.trim()) return
    setSaving(true)
    setMessage('')
    try {
      const payload = buildPayload()
      const apiKeyEnv = envNameFromRef(fApiKeyRef) || defaultApiKeyEnv(payload.provider || 'custom')
      if (fApiKeyValue.trim()) {
        await api.hermesSaveModelBinding({
          provider_id: payload.provider || 'custom',
          provider_name: providers.find(p => p.id === payload.provider)?.name || payload.provider || 'Custom',
          api_base: payload.api_base || '',
          api_key: fApiKeyValue.trim(),
          api_key_env: apiKeyEnv,
          model_id: payload.id,
          display_name: payload.display_name,
          tier: payload.tier,
          context_length: payload.context_length,
          capabilities: payload.capabilities,
          suitable_complexity: payload.suitable_complexity,
          description: payload.description,
        })
        if (!payload.active) {
          await api.updateModel(payload.id, { active: false, api_key_ref: apiKeyRefFromEnv(apiKeyEnv) })
        }
        setMessage(editingId ? t('modelUpdated') : t('modelCreated'))
      } else if (editingId) {
        await api.updateModel(editingId, payload)
        setMessage(t('modelUpdated'))
      } else {
        await api.createModel(payload as ModelDef)
        setMessage(t('modelCreated'))
      }
      cancelForm()
      try {
        await load()
      } catch {
        // keep the success message even if refresh fails
      }
    } catch (e: any) {
      setMessage(`${t('modelSaveFailed')}: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm(lang === 'zh' ? `确定删除模型 ${id}？` : `Delete model ${id}?`)) return
    setSaving(true)
    setMessage('')
    try {
      await api.deleteModel(id)
      setMessage(t('modelDeleted'))
      await load()
    } catch (e: any) {
      setMessage(`${t('modelDeleteFailed')}: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  const startKeyEdit = (m: ModelDef) => {
    const provider = providers.find(p => p.id === m.provider)
    setKeyEditingId(m.id)
    setKeyEnv(envNameFromRef(m.api_key_ref) || envNameFromRef(provider?.api_key_ref) || defaultApiKeyEnv(m.provider))
    setKeyValue('')
    setMessage('')
  }

  const cancelKeyEdit = () => {
    setKeyEditingId(null)
    setKeyEnv('')
    setKeyValue('')
  }

  const saveApiKey = async (m: ModelDef) => {
    const env = envNameFromRef(keyEnv)
    if (!env || !keyValue.trim()) return
    setSaving(true)
    setMessage('')
    try {
      await api.hermesSaveModelBinding({
        provider_id: m.provider || 'custom',
        provider_name: providers.find(p => p.id === m.provider)?.name || m.provider || 'Custom',
        api_base: m.api_base || '',
        api_key: keyValue.trim(),
        api_key_env: env,
        model_id: m.id,
        display_name: m.display_name || m.id,
        tier: m.tier,
        context_length: m.context_length,
        capabilities: m.capabilities,
        suitable_complexity: m.suitable_complexity,
        description: m.description,
      })
      if (!m.active) {
        await api.updateModel(m.id, { active: m.active, api_key_ref: apiKeyRefFromEnv(env) })
      }
      setMessage(t('modelKeyUpdated'))
      cancelKeyEdit()
      try {
        await load()
      } catch {
        setModels(current => current.map(item => item.id === m.id ? { ...item, api_key_ref: apiKeyRefFromEnv(env) } : item))
      }
    } catch (e: any) {
      setMessage(`${t('modelKeyUpdateFailed')}: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  // Only show models that have been configured (api_base is set)
  const configuredModels = useMemo(() =>
    models.filter(m => m.api_base && m.api_base.trim()),
    [models]
  )

  // Models for the currently selected provider (from catalog)
  const providerCatalogModels = useMemo(() => {
    const cp = catalog.find((p: any) => (p.slug || p.id) === fProvider)
    return cp?.models ?? []
  }, [catalog, fProvider])

  // Mainstream providers to show in the dropdown
  const MAINSTREAM_PROVIDERS = new Set([
    'openai', 'openai-api',
    'anthropic',
    'google', 'gemini',
    'deepseek',
    'xai', 'grok',
    'alibaba', 'qwen',
    'zhipu', 'zai', 'glm',
    'xiaomi', 'mi',
    'meta', 'llama',
    'mistral',
  ])

  const catalogProviderOptions = useMemo(() => {
    const seen = new Set<string>()
    const opts: { id: string; name: string }[] = []
    for (const p of catalog) {
      const id = (p.slug || p.id || '').toLowerCase()
      if (!id || seen.has(id)) continue
      if (!MAINSTREAM_PROVIDERS.has(id)) continue
      seen.add(id)
      opts.push({ id, name: p.name || id })
    }
    // Also include providers from listModelProviders that aren't in catalog
    for (const p of providers) {
      const id = p.id.toLowerCase()
      if (!seen.has(id) && MAINSTREAM_PROVIDERS.has(id)) {
        seen.add(id)
        opts.push({ id: p.id, name: p.name })
      }
    }
    // Always include the currently selected provider (for editing non-mainstream models)
    if (fProvider && !seen.has(fProvider.toLowerCase())) {
      opts.push({ id: fProvider, name: fProvider })
    }
    return opts
  }, [catalog, providers, fProvider])

  const chooseProvider = (nextProvider: string) => {
    setFProvider(nextProvider)
    // Try to auto-fill api_base from catalog or provider list
    const cp = catalog.find((p: any) => (p.slug || p.id) === nextProvider)
    const pp = providers.find(p => p.id === nextProvider)
    if (!fApiBase.trim()) {
      setFApiBase(cp?.api_base || pp?.api_base || '')
    }
    if (!fApiKeyRef.trim()) {
      setFApiKeyRef(cp?.api_key_ref || pp?.api_key_ref || '')
    }
  }

  const chooseCatalogModel = (modelId: string) => {
    if (!modelId) {
      setFCustomModelId(false)
      setFId('')
      setFDisplayName('')
      return
    }
    if (modelId === '__custom__') {
      setFCustomModelId(true)
      setFId('')
      setFDisplayName('')
      return
    }
    setFCustomModelId(false)
    setFId(modelId)
    const cm = providerCatalogModels.find((m: any) => (typeof m === 'string' ? m === modelId : m.id === modelId))
    if (cm && typeof cm === 'object') {
      setFDisplayName(cm.display_name || modelId)
      setFTier(cm.tier || 'standard')
      setFContextLength(cm.context_length || 128000)
      setFVision(cm.capabilities?.vision || false)
      setFTools(cm.capabilities?.tool_calling ?? true)
      setFImageGen(cm.capabilities?.image_gen || false)
      setFAudioStt(cm.capabilities?.audio_stt || false)
      setFSimple((cm.suitable_complexity || []).includes('SIMPLE'))
      setFMedium((cm.suitable_complexity || []).includes('MEDIUM'))
      setFComplex((cm.suitable_complexity || []).includes('COMPLEX'))
      setFDescription(cm.description || '')
      if (!fApiBase.trim()) setFApiBase(cm.api_base || '')
    }
  }

  const showForm = adding || editingId !== null

  // Trigger catalog load when form opens
  useEffect(() => {
    if (showForm) loadCatalog()
  }, [showForm, loadCatalog])

  const tierOptions = ['budget', 'standard', 'premium']

  if (state === 'loading') return <LoadingBlock />
  if (state === 'error') return <ErrorBlock message={error} onRetry={() => load()} />

  return (
    <div>
      <PageHeader
        title={t('modelConfigTitle')}
        subtitle={t('modelConfigSubtitle')}
        action={<>
          <span className={`text-xs ${message.includes('失败') || message.includes('failed') ? 'text-red-400' : 'text-green-400'}`}>{message}</span>
          <button className="btn-secondary text-xs" onClick={load}>{t('refresh')}</button>
          {!showForm && <button className="btn-primary text-xs" onClick={startAdd}>{t('addModel')}</button>}
        </>}
      />

      {showForm && (
        <div className="card mb-4 border-opc-accent/40 bg-opc-accent/5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">
              {editingId ? `${t('editModel')}: ${editingId}` : t('addModelTitle')}
            </h3>
            <button className="btn-secondary text-xs" onClick={cancelForm}>{t('cancel')}</button>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <label className="block">
              <span className="mb-1 block text-xs text-opc-text-2">{t('modelIdRequired')}</span>
              {providerCatalogModels.length > 0 ? (
                <select className="input" value={fCustomModelId ? '__custom__' : fId} onChange={e => chooseCatalogModel(e.target.value)} disabled={!!editingId}>
                  <option value="">{t('selectModelOption')}</option>
                  {providerCatalogModels.map((m: any) => {
                    const mid = typeof m === 'string' ? m : m.id
                    const mname = typeof m === 'string' ? m : (m.display_name || m.id)
                    return <option key={mid} value={mid}>{mname}</option>
                  })}
                  <option value="__custom__">{t('customOption')}</option>
                </select>
              ) : (
                <input className="input" value={fId} onChange={e => setFId(e.target.value)} placeholder="e.g. claude-sonnet-4" disabled={!!editingId} />
              )}
              {fCustomModelId && (
                <input className="input mt-2" value={fId} onChange={e => { setFId(e.target.value); setFDisplayName(e.target.value) }} placeholder={t('customModelIdPlaceholder')} autoFocus />
              )}
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-opc-text-2">{t('displayName')}</span>
              <input className="input" value={fDisplayName} onChange={e => setFDisplayName(e.target.value)} placeholder="e.g. Claude Sonnet 4" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-opc-text-2">{t('provider')}</span>
              <select className="input" value={fProvider} onChange={e => chooseProvider(e.target.value)}>
                <option value="">{t('selectProviderOption')}</option>
                {catalogProviderOptions.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-opc-text-2">{t('tier')}</span>
              <select className="input" value={fTier} onChange={e => setFTier(e.target.value)}>
                {tierOptions.map(tier => <option key={tier} value={tier}>{tierLabel(lang, tier)}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-opc-text-2">{t('contextLength')}</span>
              <input className="input" type="number" min="0" value={fContextLength} onChange={e => setFContextLength(Math.max(0, Number(e.target.value) || 0))} />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-opc-text-2">{t('apiBaseUrl')}</span>
              <input className="input" value={fApiBase} onChange={e => setFApiBase(e.target.value)} placeholder="https://api.example.com/v1" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-opc-text-2">{t('apiKeyRef')}</span>
              <input className="input" value={fApiKeyRef} onChange={e => setFApiKeyRef(e.target.value)} placeholder="OPENAI_API_KEY" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-opc-text-2">{t('newApiKey')}</span>
              <input className="input" type="password" value={fApiKeyValue} onChange={e => setFApiKeyValue(e.target.value)} placeholder={t('apiKeyValuePlaceholder')} autoComplete="new-password" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-opc-text-2">{t('status')}</span>
              <select className="input" value={fActive ? 'true' : 'false'} onChange={e => setFActive(e.target.value === 'true')}>
                <option value="true">{t('active')}</option>
                <option value="false">{t('inactive')}</option>
              </select>
            </label>
            <label className="block md:col-span-3">
              <span className="mb-1 block text-xs text-opc-text-2">{t('description')}</span>
              <input className="input" value={fDescription} onChange={e => setFDescription(e.target.value)} placeholder={t('modelDescriptionPlaceholder')} />
            </label>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <fieldset className="rounded-lg border border-opc-border p-3">
              <legend className="text-xs font-semibold text-opc-text-2 px-1">{t('capabilities')}</legend>
              <div className="flex flex-wrap gap-3">
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={fTools} onChange={e => setFTools(e.target.checked)} /> {t('modelCapabilityTools')}</label>
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={fVision} onChange={e => setFVision(e.target.checked)} /> {t('modelCapabilityVision')}</label>
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={fImageGen} onChange={e => setFImageGen(e.target.checked)} /> {t('modelCapabilityImageGen')}</label>
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={fAudioStt} onChange={e => setFAudioStt(e.target.checked)} /> {t('modelCapabilityAudioStt')}</label>
              </div>
            </fieldset>
            <fieldset className="rounded-lg border border-opc-border p-3">
              <legend className="text-xs font-semibold text-opc-text-2 px-1">{t('suitableComplexity')}</legend>
              <div className="flex flex-wrap gap-3">
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={fSimple} onChange={e => setFSimple(e.target.checked)} /> {t('modelComplexitySimple')}</label>
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={fMedium} onChange={e => setFMedium(e.target.checked)} /> {t('modelComplexityMedium')}</label>
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={fComplex} onChange={e => setFComplex(e.target.checked)} /> {t('modelComplexityComplex')}</label>
              </div>
            </fieldset>
          </div>
          <div className="mt-4">
            <button className="btn-primary text-xs" disabled={!fId.trim() || saving} onClick={handleSave}>
              {saving ? t('saving') : (editingId ? t('updateModel') : t('createModel'))}
            </button>
          </div>
        </div>
      )}

      {configuredModels.length === 0 && !showForm ? (
        <div className="py-16 text-center">
          <p className="text-sm text-opc-text-2 mb-4">{t('noConfiguredModels')}</p>
          <button className="btn-primary text-xs" onClick={startAdd}>{t('addModel')}</button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {configuredModels.map(m => (
            <div key={m.id} className={`card flex flex-col ${!m.active ? 'opacity-50' : ''}`}>
              <div className="flex items-start justify-between gap-2 mb-3">
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold truncate">{m.display_name || m.id}</h3>
                  <div className="font-mono text-xs text-opc-text-2 truncate">{m.id}</div>
                </div>
                <span className={`badge shrink-0 ${m.tier === 'premium' ? 'badge-accent' : m.tier === 'standard' ? 'badge-info' : 'badge-success'}`}>{tierLabel(lang, m.tier)}</span>
              </div>

              <div className="mb-3 flex flex-wrap gap-1">
                <span className="badge text-xs">{m.provider || 'custom'}</span>
                {m.context_length > 0 && <span className="badge text-xs">{Math.round(m.context_length / 1000)}K {t('contextShort')}</span>}
                {m.capabilities?.tool_calling && <span className="badge-success text-xs" aria-label={t('modelCapabilityTools')}>🔧</span>}
                {m.capabilities?.vision && <span className="badge-info text-xs" aria-label={t('modelCapabilityVision')}>👁</span>}
                {m.capabilities?.image_gen && <span className="badge-accent text-xs" aria-label={t('modelCapabilityImageGen')}>🖼</span>}
                {m.capabilities?.audio_stt && <span className="badge-warning text-xs" aria-label={t('modelCapabilityAudioStt')}>🎤</span>}
                {!m.active && <span className="badge-warning text-xs">{t('inactive')}</span>}
              </div>

              {m.api_base && (
                <div className="mb-1 text-xs text-opc-text-2 truncate" title={m.api_base}>
                  {t('apiLabel')}: {m.api_base}
                </div>
              )}
              {m.api_key_ref && m.api_key_ref !== 'null' && (
                <div className="mb-1 text-xs text-opc-text-2 truncate">
                  {t('apiKeyLabel')}: {m.api_key_ref}
                </div>
              )}
              {keyEditingId === m.id && (
                <div className="mb-3 rounded-lg border border-opc-border bg-opc-bg p-3">
                  <div className="mb-2 text-xs font-semibold text-opc-text-2">{t('editApiKey')}</div>
                  <div className="space-y-2">
                    <label className="block">
                      <span className="mb-1 block text-xs text-opc-text-2">{t('apiKeyEnv')}</span>
                      <input className="input" value={keyEnv} onChange={e => setKeyEnv(e.target.value)} placeholder="OPENAI_API_KEY" />
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-xs text-opc-text-2">{t('newApiKey')}</span>
                      <input className="input" type="password" value={keyValue} onChange={e => setKeyValue(e.target.value)} placeholder={t('apiKeyValuePlaceholder')} autoComplete="new-password" />
                    </label>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="btn-primary flex-1 justify-center text-xs" disabled={saving || !envNameFromRef(keyEnv) || !keyValue.trim()} onClick={() => saveApiKey(m)}>
                      {saving ? t('saving') : t('saveApiKey')}
                    </button>
                    <button className="btn-secondary flex-1 justify-center text-xs" disabled={saving} onClick={cancelKeyEdit}>
                      {t('cancel')}
                    </button>
                  </div>
                </div>
              )}
              {m.suitable_complexity?.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1">
                  {m.suitable_complexity.map(c => (
                    <span key={c} className="text-[10px] px-1.5 py-0.5 rounded bg-opc-surface-2 text-opc-text-2">{complexityLabel(t, c)}</span>
                  ))}
                </div>
              )}
              {m.description && (
                <p className="mb-3 text-xs text-opc-text-2 leading-relaxed flex-1">{m.description}</p>
              )}

              <div className="mt-auto flex flex-wrap gap-2 pt-3 border-t border-opc-border">
                <button className="btn-secondary text-xs flex-1 justify-center" onClick={() => startEdit(m)} disabled={saving}>
                  {t('edit')}
                </button>
                <button className="btn-secondary text-xs flex-1 justify-center" onClick={() => startKeyEdit(m)} disabled={saving || keyEditingId === m.id}>
                  {t('editApiKeyShort')}
                </button>
                <button className="btn-danger text-xs flex-1 justify-center" onClick={() => handleDelete(m.id)} disabled={saving}>
                  {t('delete')}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function profileModelSummary(profile: HermesProfileInfo) {
  const provider = asText(profile.provider).trim()
  const model = asText(profile.model).trim()
  if (provider && model) return `${provider} / ${model}`
  return model || provider || '-'
}

export function HermesProfilesPage() {
  const { lang } = useI18n()
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState('')
  const [profiles, setProfiles] = useState<HermesProfileInfo[]>([])
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [setupCommand, setSetupCommand] = useState('')
  const [soulContent, setSoulContent] = useState('')
  const [soulExists, setSoulExists] = useState(false)
  const [soulDirty, setSoulDirty] = useState(false)
  const [detailVersion, setDetailVersion] = useState(0)
  const [detailError, setDetailError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState('')
  const [form, setForm] = useState({ name: '', clone_from_default: true, no_skills: false })
  const [renameSource, setRenameSource] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  const load = useCallback(async () => {
    setState('loading')
    setError('')
    try {
      const data = await api.hermesProfiles()
      const rows = data.profiles ?? []
      setProfiles(rows)
      setSelectedName((current) => {
        if (current && rows.some((profile) => profile.name === current)) return current
        return rows[0]?.name ?? null
      })
      setState('ready')
    } catch (e: any) {
      setError(e.message)
      setState('error')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.name === selectedName) ?? null,
    [profiles, selectedName],
  )

  useEffect(() => {
    if (!selectedName) {
      setSetupCommand('')
      setSoulContent('')
      setSoulExists(false)
      setSoulDirty(false)
      setDetailError('')
      return
    }
    let active = true
    setDetailError('')
    setSetupCommand('')
    setSoulDirty(false)
    Promise.all([
      api.hermesProfileSetupCommand(selectedName),
      api.hermesProfileSoul(selectedName),
    ]).then(([setup, soul]) => {
      if (!active) return
      setSetupCommand(setup.command || '')
      setSoulContent(soul.content || '')
      setSoulExists(!!soul.exists)
    }).catch((e: any) => {
      if (!active) return
      setDetailError(e.message)
      setSoulContent('')
      setSoulExists(false)
    })
    return () => { active = false }
  }, [selectedName, detailVersion])

  const createProfile = async () => {
    const name = form.name.trim()
    if (!name) return
    setBusy('create')
    setMessage('')
    try {
      await api.hermesCreateProfile({
        name,
        clone_from_default: form.clone_from_default,
        no_skills: form.clone_from_default ? false : form.no_skills,
      })
      setForm({ name: '', clone_from_default: true, no_skills: false })
      setSelectedName(name)
      setMessage(lang === 'zh' ? 'Profile 已创建' : 'Profile created')
      await load()
    } catch (e: any) {
      setMessage(`${lang === 'zh' ? '创建失败' : 'Create failed'}: ${e.message}`)
    } finally {
      setBusy('')
    }
  }

  const startRename = (profile: HermesProfileInfo) => {
    setRenameSource(profile.name)
    setRenameValue(profile.name)
    setMessage('')
  }

  const saveRename = async (profile: HermesProfileInfo) => {
    const newName = renameValue.trim()
    if (!newName || newName === profile.name) {
      setRenameSource(null)
      return
    }
    setBusy(`rename-${profile.name}`)
    setMessage('')
    try {
      await api.hermesRenameProfile(profile.name, newName)
      setRenameSource(null)
      setSelectedName(newName)
      setMessage(lang === 'zh' ? 'Profile 已重命名' : 'Profile renamed')
      await load()
    } catch (e: any) {
      setMessage(`${lang === 'zh' ? '重命名失败' : 'Rename failed'}: ${e.message}`)
    } finally {
      setBusy('')
    }
  }

  const deleteProfile = async (profile: HermesProfileInfo) => {
    if (profile.is_default) return
    const confirmed = window.confirm(lang === 'zh' ? `确定删除 Profile ${profile.name}？` : `Delete profile ${profile.name}?`)
    if (!confirmed) return
    setBusy(`delete-${profile.name}`)
    setMessage('')
    try {
      await api.hermesDeleteProfile(profile.name)
      if (selectedName === profile.name) setSelectedName(null)
      setMessage(lang === 'zh' ? 'Profile 已删除' : 'Profile deleted')
      await load()
    } catch (e: any) {
      setMessage(`${lang === 'zh' ? '删除失败' : 'Delete failed'}: ${e.message}`)
    } finally {
      setBusy('')
    }
  }

  const saveSoul = async () => {
    if (!selectedName) return
    setBusy('soul')
    setMessage('')
    try {
      await api.hermesSaveProfileSoul(selectedName, soulContent)
      setSoulDirty(false)
      setSoulExists(true)
      setMessage(lang === 'zh' ? 'SOUL.md 已保存' : 'SOUL.md saved')
    } catch (e: any) {
      setMessage(`${lang === 'zh' ? '保存失败' : 'Save failed'}: ${e.message}`)
    } finally {
      setBusy('')
    }
  }

  const copySetupCommand = async () => {
    if (!setupCommand) return
    try {
      await navigator.clipboard.writeText(setupCommand)
      setMessage(lang === 'zh' ? '命令已复制' : 'Command copied')
    } catch {
      setMessage(setupCommand)
    }
  }

  if (state === 'loading') return <LoadingBlock />
  if (state === 'error') return <ErrorBlock message={error} onRetry={load} />

  return (
    <div>
      <PageHeader
        title={lang === 'zh' ? 'Hermes Profiles' : 'Hermes Profiles'}
        subtitle={lang === 'zh' ? '管理原生 Hermes Profile，支持创建、重命名、删除、查看 setup 命令和编辑 SOUL.md。' : 'Manage native Hermes profiles, setup commands, and SOUL.md content.'}
        action={<>
          <span className={`text-xs ${message.includes('失败') || message.includes('failed') ? 'text-red-400' : 'text-green-400'}`}>{message}</span>
          <button className="btn-secondary text-xs" onClick={load}>{lang === 'zh' ? '刷新' : 'Refresh'}</button>
        </>}
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold">{lang === 'zh' ? '新建 Profile' : 'New Profile'}</h3>
            <div className="space-y-3">
              <input
                className="input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder={lang === 'zh' ? 'profile-name' : 'profile-name'}
              />
              <label className="flex items-center gap-2 text-xs text-opc-text-2">
                <input
                  type="checkbox"
                  checked={form.clone_from_default}
                  onChange={(e) => setForm({ ...form, clone_from_default: e.target.checked, no_skills: e.target.checked ? false : form.no_skills })}
                />
                {lang === 'zh' ? '从 default 复制配置和技能' : 'Clone config and skills from default'}
              </label>
              <label className="flex items-center gap-2 text-xs text-opc-text-2">
                <input
                  type="checkbox"
                  checked={form.no_skills}
                  disabled={form.clone_from_default}
                  onChange={(e) => setForm({ ...form, no_skills: e.target.checked })}
                />
                {lang === 'zh' ? '创建空技能 Profile' : 'Create without bundled skills'}
              </label>
              <button className="btn-primary w-full justify-center text-xs" disabled={busy === 'create' || !form.name.trim()} onClick={createProfile}>
                {busy === 'create' ? (lang === 'zh' ? '创建中...' : 'Creating...') : (lang === 'zh' ? '创建' : 'Create')}
              </button>
            </div>
          </div>

          <div className="space-y-3">
            {profiles.length ? profiles.map((profile) => {
              const selected = profile.name === selectedName
              const renaming = renameSource === profile.name
              return (
                <div key={profile.name} className={`card ${selected ? 'border-opc-accent/50 bg-opc-accent/5' : ''}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-semibold">{profile.name}</div>
                      <div className="mt-1 truncate font-mono text-xs text-opc-text-2">{profile.path}</div>
                    </div>
                    <StatusBadge active={profile.has_env} trueLabel=".env" falseLabel="no .env" />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {profile.is_default && <span className="badge-accent text-xs">default</span>}
                    <span className="badge text-xs">{profile.skill_count} skills</span>
                    <span className="badge-info text-xs">{profileModelSummary(profile)}</span>
                  </div>

                  {renaming ? (
                    <div className="mt-3 space-y-2">
                      <input className="input" value={renameValue} onChange={(e) => setRenameValue(e.target.value)} autoFocus />
                      <div className="flex gap-2">
                        <button className="btn-primary flex-1 justify-center text-xs" disabled={busy === `rename-${profile.name}` || !renameValue.trim()} onClick={() => saveRename(profile)}>{lang === 'zh' ? '保存' : 'Save'}</button>
                        <button className="btn-secondary flex-1 justify-center text-xs" disabled={busy === `rename-${profile.name}`} onClick={() => setRenameSource(null)}>{lang === 'zh' ? '取消' : 'Cancel'}</button>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-4 flex flex-wrap gap-2 border-t border-opc-border pt-3">
                      <button className="btn-secondary flex-1 justify-center text-xs" onClick={() => setSelectedName(profile.name)}>{lang === 'zh' ? '查看' : 'View'}</button>
                      <button className="btn-secondary flex-1 justify-center text-xs" disabled={profile.is_default || !!busy} onClick={() => startRename(profile)}>{lang === 'zh' ? '重命名' : 'Rename'}</button>
                      <button className="btn-danger flex-1 justify-center text-xs" disabled={profile.is_default || !!busy} onClick={() => deleteProfile(profile)}>{lang === 'zh' ? '删除' : 'Delete'}</button>
                    </div>
                  )}
                </div>
              )
            }) : <div className="card"><EmptyBlock label={lang === 'zh' ? '暂无 Profile' : 'No profiles'} /></div>}
          </div>
        </div>

        <div className="card">
          {selectedProfile ? (
            <div>
              <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0">
                  <h3 className="truncate text-base font-semibold">{selectedProfile.name}</h3>
                  <div className="mt-1 truncate font-mono text-xs text-opc-text-2">{selectedProfile.path}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {selectedProfile.is_default && <span className="badge-accent text-xs">default</span>}
                  <StatusBadge active={selectedProfile.has_env} trueLabel={lang === 'zh' ? '有 .env' : 'Has .env'} falseLabel={lang === 'zh' ? '无 .env' : 'No .env'} />
                </div>
              </div>

              {detailError && <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-400">{detailError}</div>}

              <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-opc-border bg-opc-bg p-3">
                  <div className="text-xs text-opc-text-2">{lang === 'zh' ? '模型' : 'Model'}</div>
                  <div className="mt-1 truncate font-mono text-sm">{profileModelSummary(selectedProfile)}</div>
                </div>
                <div className="rounded-lg border border-opc-border bg-opc-bg p-3">
                  <div className="text-xs text-opc-text-2">{lang === 'zh' ? '技能数量' : 'Skills'}</div>
                  <div className="mt-1 text-sm font-semibold">{selectedProfile.skill_count}</div>
                </div>
                <div className="rounded-lg border border-opc-border bg-opc-bg p-3">
                  <div className="text-xs text-opc-text-2">{lang === 'zh' ? '类型' : 'Type'}</div>
                  <div className="mt-1 text-sm font-semibold">{selectedProfile.is_default ? 'default' : 'named'}</div>
                </div>
              </div>

              <div className="mb-4 rounded-lg border border-opc-border bg-opc-bg p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-xs font-semibold text-opc-text-2">{lang === 'zh' ? 'Setup 命令' : 'Setup Command'}</div>
                  <button className="btn-secondary text-xs" disabled={!setupCommand} onClick={copySetupCommand}>{lang === 'zh' ? '复制' : 'Copy'}</button>
                </div>
                <pre className="overflow-auto rounded-md bg-opc-surface-2 p-3 font-mono text-sm text-opc-text">{setupCommand || '-'}</pre>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold">SOUL.md</h3>
                    <p className="mt-1 text-xs text-opc-text-2">{soulExists ? (lang === 'zh' ? '已存在' : 'Existing file') : (lang === 'zh' ? '保存后创建文件' : 'Will be created on save')}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="btn-secondary text-xs" disabled={!soulDirty || busy === 'soul'} onClick={() => setDetailVersion((value) => value + 1)}>{lang === 'zh' ? '撤销' : 'Revert'}</button>
                    <button className="btn-primary text-xs" disabled={!soulDirty || busy === 'soul'} onClick={saveSoul}>{busy === 'soul' ? (lang === 'zh' ? '保存中...' : 'Saving...') : (lang === 'zh' ? '保存' : 'Save')}</button>
                  </div>
                </div>
                <textarea
                  className="h-[460px] w-full resize-none rounded-lg border border-opc-border bg-opc-bg p-4 font-mono text-sm leading-6 text-opc-text focus:border-opc-accent/50 focus:outline-none"
                  value={soulContent}
                  onChange={(e) => { setSoulContent(e.target.value); setSoulDirty(true) }}
                  spellCheck={false}
                />
              </div>
            </div>
          ) : (
            <EmptyBlock label={lang === 'zh' ? '请选择 Profile' : 'Select a profile'} />
          )}
        </div>
      </div>
    </div>
  )
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
