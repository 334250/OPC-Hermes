import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

type PanelKey =
  | 'chat'
  | 'sessions'
  | 'analytics'
  | 'models'
  | 'logs'
  | 'cron'
  | 'skills'
  | 'plugins'
  | 'profiles'
  | 'config'
  | 'keys'
  | 'documentation'

const PANEL_LABELS: Record<PanelKey, { zh: string; en: string }> = {
  chat: { zh: 'Chat', en: 'Chat' },
  sessions: { zh: '会话', en: 'Sessions' },
  analytics: { zh: '分析', en: 'Analytics' },
  models: { zh: '模型', en: 'Models' },
  logs: { zh: '日志', en: 'Logs' },
  cron: { zh: '定时任务', en: 'Cron' },
  skills: { zh: '技能', en: 'Skills' },
  plugins: { zh: '插件', en: 'Plugins' },
  profiles: { zh: 'Profiles', en: 'Profiles' },
  config: { zh: '配置', en: 'Config' },
  keys: { zh: 'Keys', en: 'Keys' },
  documentation: { zh: '文档', en: 'Documentation' },
}

const PANEL_SUBTITLES: Record<PanelKey, { zh: string; en: string }> = {
  chat: {
    zh: '复用 Hermes 会话与运行状态能力，作为 Chat/会话入口的数据面板。',
    en: 'Reuses Hermes session and runtime status capabilities for the chat surface.',
  },
  sessions: {
    zh: '查看 Hermes 原生会话、活跃状态和轨迹摘要。',
    en: 'Inspect native Hermes sessions, activity state, and trace summaries.',
  },
  analytics: {
    zh: '查看 Hermes 使用量和模型统计。',
    en: 'Review Hermes usage and model analytics.',
  },
  models: {
    zh: '查看当前模型、可选模型和辅助模型配置。',
    en: 'Inspect active, available, and auxiliary model configuration.',
  },
  logs: {
    zh: '查看 Hermes 原生日志尾部。',
    en: 'Read the native Hermes log tail.',
  },
  cron: {
    zh: '查看并触发、暂停或恢复 Hermes 定时任务。',
    en: 'List, trigger, pause, and resume Hermes cron jobs.',
  },
  skills: {
    zh: '查看并启用/禁用 Hermes 技能。',
    en: 'View and enable or disable Hermes skills.',
  },
  plugins: {
    zh: '查看 Hermes Dashboard 插件并重新扫描。',
    en: 'View Hermes dashboard plugins and rescan the registry.',
  },
  profiles: {
    zh: '查看 Hermes Profiles。',
    en: 'Inspect Hermes profiles.',
  },
  config: {
    zh: '查看 Hermes 原生配置、默认值和配置 schema。',
    en: 'Inspect native Hermes config, defaults, and schema.',
  },
  keys: {
    zh: '查看 Hermes 环境变量与 Key 状态。',
    en: 'Inspect Hermes environment variable and key status.',
  },
  documentation: {
    zh: '查看 Hermes 状态、配置 schema 和 API 文档入口。',
    en: 'Review Hermes status, config schema, and API documentation entry points.',
  },
}

async function loadPanelData(panel: PanelKey) {
  switch (panel) {
    case 'chat':
      return {
        status: await api.hermes('/status'),
        sessions: await api.hermes('/sessions?limit=10'),
      }
    case 'sessions':
      return api.hermes('/sessions?limit=30')
    case 'analytics': {
      const [usage, models] = await Promise.all([
        api.hermes('/analytics/usage'),
        api.hermes('/analytics/models'),
      ])
      return { usage, models }
    }
    case 'models': {
      const [info, options, auxiliary] = await Promise.all([
        api.hermes('/model/info'),
        api.hermes('/model/options'),
        api.hermes('/model/auxiliary'),
      ])
      return { info, options, auxiliary }
    }
    case 'logs':
      return api.hermes('/logs?lines=200')
    case 'cron':
      return api.hermes('/cron/jobs')
    case 'skills': {
      const [skills, toolsets] = await Promise.all([
        api.hermes('/skills'),
        api.hermes('/tools/toolsets'),
      ])
      return { skills, toolsets }
    }
    case 'plugins':
      return api.hermes('/dashboard/plugins')
    case 'profiles':
      return api.hermes('/profiles')
    case 'config': {
      const [config, defaults, schema] = await Promise.all([
        api.hermes('/config'),
        api.hermes('/config/defaults'),
        api.hermes('/config/schema'),
      ])
      return { config, defaults, schema }
    }
    case 'keys':
      return api.hermes('/env')
    case 'documentation': {
      const [status, schema] = await Promise.all([
        api.hermes('/status'),
        api.hermes('/config/schema'),
      ])
      return { status, schema, apiDocs: '/docs' }
    }
  }
}

function asArray(data: any): any[] {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.sessions)) return data.sessions
  if (Array.isArray(data?.skills)) return data.skills
  if (Array.isArray(data?.profiles)) return data.profiles
  if (Array.isArray(data?.plugins)) return data.plugins
  return []
}

function getName(item: any) {
  return item?.name || item?.id || item?.session_id || item?.title || item?.label || 'item'
}

export default function HermesPanel() {
  const { panel } = useParams<{ panel: string }>()
  const location = useLocation()
  const { lang, t } = useI18n()
  const pathPanel = location.pathname.split('/').filter(Boolean).pop() || 'sessions'
  const rawPanel = panel || (pathPanel === 'env' ? 'keys' : pathPanel)
  const panelKey = (PANEL_LABELS[rawPanel as PanelKey] ? rawPanel : 'sessions') as PanelKey
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)

  const title = PANEL_LABELS[panelKey][lang]
  const subtitle = PANEL_SUBTITLES[panelKey][lang]

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    loadPanelData(panelKey)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [panelKey])

  useEffect(() => {
    reload()
  }, [reload])

  const rows = useMemo(() => asArray(data), [data])

  const runAction = async (key: string, fn: () => Promise<any>) => {
    setBusyAction(key)
    try {
      await fn()
      reload()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusyAction(null)
    }
  }

  if (loading) {
    return <div className="card animate-pulse"><div className="h-96 rounded-lg bg-opc-surface-2" /></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-xl font-semibold">{title}</h2>
          <p className="mt-1 max-w-3xl text-sm text-opc-text-2">{subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {panelKey === 'plugins' && (
            <button
              className="btn-secondary text-xs"
              disabled={busyAction === 'rescan'}
              onClick={() => runAction('rescan', () => api.hermes('/dashboard/plugins/rescan'))}
            >
              {lang === 'zh' ? '重新扫描' : 'Rescan'}
            </button>
          )}
          {panelKey === 'documentation' && (
            <a className="btn-secondary text-xs" href="/docs" target="_blank" rel="noreferrer">
              {t('apiDocs')}
            </a>
          )}
          <button className="btn-secondary text-xs" onClick={reload}>{lang === 'zh' ? '刷新' : 'Refresh'}</button>
        </div>
      </div>

      {error && (
        <div className="card border-opc-error/50 bg-opc-error/5">
          <p className="text-sm text-red-400">{t('failedToLoad')}: {error}</p>
        </div>
      )}

      {rows.length > 0 && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {rows.slice(0, 20).map((item, index) => (
            <div key={`${getName(item)}-${index}`} className="card">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-sm font-semibold">{getName(item)}</h3>
                  <p className="mt-1 line-clamp-2 text-xs text-opc-text-2">
                    {item?.description || item?.summary || item?.model || item?.schedule || item?.status || '—'}
                  </p>
                </div>
                {item?.enabled !== undefined && (
                  <span className={item.enabled ? 'badge-success' : 'badge-warning'}>
                    {item.enabled ? (lang === 'zh' ? '启用' : 'Enabled') : (lang === 'zh' ? '停用' : 'Disabled')}
                  </span>
                )}
              </div>
              {panelKey === 'cron' && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    className="btn-secondary text-xs"
                    disabled={busyAction === `trigger-${item.id}`}
                    onClick={() => runAction(`trigger-${item.id}`, () => api.hermes(`/cron/jobs/${encodeURIComponent(item.id)}/trigger`, { method: 'POST' }))}
                  >
                    {lang === 'zh' ? '触发' : 'Trigger'}
                  </button>
                  <button
                    className="btn-secondary text-xs"
                    disabled={busyAction === `pause-${item.id}`}
                    onClick={() => runAction(`pause-${item.id}`, () => api.hermes(`/cron/jobs/${encodeURIComponent(item.id)}/pause`, { method: 'POST' }))}
                  >
                    {lang === 'zh' ? '暂停' : 'Pause'}
                  </button>
                  <button
                    className="btn-secondary text-xs"
                    disabled={busyAction === `resume-${item.id}`}
                    onClick={() => runAction(`resume-${item.id}`, () => api.hermes(`/cron/jobs/${encodeURIComponent(item.id)}/resume`, { method: 'POST' }))}
                  >
                    {lang === 'zh' ? '恢复' : 'Resume'}
                  </button>
                </div>
              )}
              {panelKey === 'skills' && item?.name && (
                <button
                  className="btn-secondary mt-4 text-xs"
                  disabled={busyAction === `skill-${item.name}`}
                  onClick={() => runAction(`skill-${item.name}`, () => api.hermes('/skills/toggle', {
                    method: 'PUT',
                    body: JSON.stringify({ name: item.name, enabled: !item.enabled }),
                  }))}
                >
                  {item.enabled ? (lang === 'zh' ? '禁用' : 'Disable') : (lang === 'zh' ? '启用' : 'Enable')}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-opc-text-2">
            {lang === 'zh' ? '原始数据' : 'Raw Data'}
          </h3>
          {rows.length > 20 && <span className="text-xs text-opc-text-2">{rows.length}</span>}
        </div>
        {panelKey === 'logs' && Array.isArray(data?.lines) ? (
          <pre className="max-h-[520px] overflow-auto rounded-lg bg-opc-bg p-4 text-xs leading-5 text-opc-text-2">
            {data.lines.join('\n') || (lang === 'zh' ? '暂无日志' : 'No logs')}
          </pre>
        ) : (
          <pre className="max-h-[520px] overflow-auto rounded-lg bg-opc-bg p-4 text-xs leading-5 text-opc-text-2">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}
