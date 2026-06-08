import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

type ConfigData = Record<string, any>

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="rounded-xl border border-opc-border bg-opc-surface">
      <button className="flex w-full items-center justify-between px-5 py-4 text-left text-sm font-semibold hover:bg-opc-surface-2/50 transition-colors rounded-t-xl" onClick={() => setOpen(!open)}>
        {title}
        <span className="text-xs text-opc-text-2">{open ? '▾' : '▸'}</span>
      </button>
      {open && <div className="px-5 pb-5 space-y-4">{children}</div>}
    </div>
  )
}

function Toggle({ label, desc, value, onChange }: { label: string; desc?: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <input type="checkbox" checked={value} onChange={e => onChange(e.target.checked)} className="mt-0.5 h-4 w-4 rounded border-opc-border bg-opc-surface-2 accent-opc-accent" />
      <div>
        <div className="text-sm font-medium">{label}</div>
        {desc && <div className="text-xs text-opc-text-2 mt-0.5">{desc}</div>}
      </div>
    </label>
  )
}

function TextInput({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div>
      <label className="block text-xs font-medium text-opc-text-2 mb-1.5">{label}</label>
      <input type="text" className="input" value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
    </div>
  )
}

function NumberInput({ label, value, onChange, min, max }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number }) {
  return (
    <div>
      <label className="block text-xs font-medium text-opc-text-2 mb-1.5">{label}</label>
      <input type="number" className="input" value={value} onChange={e => onChange(Number(e.target.value))} min={min} max={max} />
    </div>
  )
}

function SelectInput({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div>
      <label className="block text-xs font-medium text-opc-text-2 mb-1.5">{label}</label>
      <select className="input" value={value} onChange={e => onChange(e.target.value)}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

function TagList({ label, values, onChange, placeholder }: { label: string; values: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [input, setInput] = useState('')
  const add = () => {
    const v = input.trim()
    if (v && !values.includes(v)) { onChange([...values, v]); setInput('') }
  }
  return (
    <div>
      <label className="block text-xs font-medium text-opc-text-2 mb-1.5">{label}</label>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {values.map(v => (
          <span key={v} className="badge-accent flex items-center gap-1 text-xs">{v}<button onClick={() => onChange(values.filter(x => x !== v))} className="hover:text-red-400">&times;</button></span>
        ))}
      </div>
      <div className="flex gap-2">
        <input className="input flex-1 text-xs" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), add())} placeholder={placeholder} />
        <button onClick={add} className="btn-secondary text-xs">Add</button>
      </div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-2 border-b border-opc-border last:border-0">
      <span className="text-xs text-opc-text-2">{label}</span>
      <span className="text-xs font-mono text-right">{value || '—'}</span>
    </div>
  )
}

export default function Config() {
  const { t } = useI18n()
  const [config, setConfig] = useState<ConfigData>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => { api.getConfig().then(d => setConfig(d.config ?? {})).finally(() => setLoading(false)) }, [])

  const set = useCallback((key: string, value: any) => {
    setConfig(prev => { const keys = key.split('.'); const next = { ...prev }; let obj: any = next; for (let i = 0; i < keys.length - 1; i++) { if (!obj[keys[i]] || typeof obj[keys[i]] !== 'object') obj[keys[i]] = {}; obj = obj[keys[i]] }; obj[keys[keys.length - 1]] = value; return next })
  }, [])

  const save = async () => {
    setSaving(true)
    try { await api.updateConfig(config); setMessage(t('saved')); setTimeout(() => setMessage(''), 2000) }
    catch (e: any) { setMessage(`Error: ${e.message}`) }
    finally { setSaving(false) }
  }

  if (loading) return <div className="card animate-pulse"><div className="h-96 bg-opc-surface-2 rounded" /></div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">{t('configuration')}</h2>
        <div className="flex items-center gap-3">
          {message && <span className={`text-xs ${message.startsWith('Error') ? 'text-red-400' : 'text-green-400'}`}>{message}</span>}
          <button onClick={save} className="btn-primary text-xs" disabled={saving}>{t('save')}</button>
        </div>
      </div>

      <div className="space-y-4">
        <Section title={t('cfgGeneral')}>
          <Toggle label={t('cfgEnable')} desc={t('cfgEnableDesc')} value={config.enabled ?? true} onChange={v => set('enabled', v)} />
          <TextInput label={t('cfgLeaderModel')} value={config.leader_model ?? ''} onChange={v => set('leader_model', v)} placeholder="${HERMES_DEFAULT_MODEL}" />
          <Toggle label={t('cfgAllowExternal')} desc={t('cfgAllowExternalDesc')} value={config.allow_external_runtime_paths ?? false} onChange={v => set('allow_external_runtime_paths', v)} />
          <div className="grid grid-cols-2 gap-4">
            <InfoRow label={t('cfgAgentPath')} value={config.agent_list_path ?? 'auto'} />
            <InfoRow label={t('cfgMemoryPath')} value={config.memory_path ?? 'auto'} />
            <InfoRow label={t('cfgArtifactPath')} value={config.artifact_path ?? 'auto'} />
            <InfoRow label={t('cfgProposalPath')} value={config.proposal_path ?? 'auto'} />
            <InfoRow label={t('cfgLogPath')} value={config.log_path ?? 'auto'} />
          </div>
        </Section>

        <Section title={t('cfgRouting')}>
          <TagList label={t('cfgTriggerPrefixes')} values={config.routing?.trigger_prefixes ?? ['/opc']} onChange={v => set('routing.trigger_prefixes', v)} placeholder="/opc" />
          <Toggle label={t('cfgAutoRoute')} desc={t('cfgAutoRouteDesc')} value={config.routing?.auto_route_complex_tasks ?? false} onChange={v => set('routing.auto_route_complex_tasks', v)} />
          <TagList label={t('cfgRequireApproval')} values={config.routing?.require_approval_for ?? ['MEDIUM', 'COMPLEX']} onChange={v => set('routing.require_approval_for', v)} placeholder="MEDIUM" />
        </Section>

        <Section title={t('cfgModelPrefs')}>
          <TextInput label={t('cfgPreferredProvider')} value={config.model_preferences?.global?.preferred_provider ?? ''} onChange={v => set('model_preferences.global.preferred_provider', v)} placeholder={t('cfgProviderPlaceholder')} />
          <NumberInput label={t('cfgMaxCost')} value={config.model_preferences?.global?.max_cost_per_call ?? 0} onChange={v => set('model_preferences.global.max_cost_per_call', v || null)} min={0} />
        </Section>

        <Section title={t('cfgEvaluator')}>
          <Toggle label={t('cfgEvalEnable')} desc={t('cfgEvalEnableDesc')} value={config.evaluator?.enabled ?? true} onChange={v => set('evaluator.enabled', v)} />
          <TextInput label={t('cfgEvalModel')} value={config.evaluator?.model ?? 'claude-sonnet-4'} onChange={v => set('evaluator.model', v)} placeholder="claude-sonnet-4" />
          <div className="grid grid-cols-3 gap-4">
            <NumberInput label={t('cfgEvalOverall')} value={config.evaluator?.scoring_thresholds?.overall ?? 0.7} onChange={v => set('evaluator.scoring_thresholds.overall', v)} min={0} max={1} />
            <NumberInput label={t('cfgEvalAccuracy')} value={config.evaluator?.scoring_thresholds?.accuracy ?? 0.8} onChange={v => set('evaluator.scoring_thresholds.accuracy', v)} min={0} max={1} />
            <NumberInput label={t('cfgEvalLeader')} value={config.evaluator?.scoring_thresholds?.leader_decomposition ?? 0.6} onChange={v => set('evaluator.scoring_thresholds.leader_decomposition', v)} min={0} max={1} />
          </div>
        </Section>

        <Section title={t('cfgOptimizer')}>
          <Toggle label={t('cfgOptEnable')} desc={t('cfgOptEnableDesc')} value={config.optimizer?.enabled ?? true} onChange={v => set('optimizer.enabled', v)} />
          <SelectInput label={t('cfgOptInterval')} value={config.optimizer?.cron_interval ?? '1h'} onChange={v => set('optimizer.cron_interval', v)} options={[
            { value: '30m', label: t('cfgInterval30m') }, { value: '1h', label: t('cfgInterval1h') },
            { value: '6h', label: t('cfgInterval6h') }, { value: '24h', label: t('cfgInterval24h') },
          ]} />
          <Toggle label={t('cfgOptPush')} desc={t('cfgOptPushDesc')} value={config.optimizer?.proposal?.push_to_dashboard ?? true} onChange={v => set('optimizer.proposal.push_to_dashboard', v)} />
          <NumberInput label={t('cfgOptDedupe')} value={config.optimizer?.proposal?.dedupe_window_days ?? 30} onChange={v => set('optimizer.proposal.dedupe_window_days', v)} min={1} max={365} />
        </Section>

        <Section title={t('cfgKnowledge')}>
          <Toggle label={t('cfgKbEnable')} desc={t('cfgKbEnableDesc')} value={config.knowledge_pipeline?.enabled ?? false} onChange={v => set('knowledge_pipeline.enabled', v)} />
          <Toggle label={t('cfgKbChroma')} desc={t('cfgKbChromaDesc')} value={config.knowledge_pipeline?.use_chromadb ?? false} onChange={v => set('knowledge_pipeline.use_chromadb', v)} />
          <SelectInput label={t('cfgKbCrawl')} value={config.knowledge_pipeline?.crawl_interval ?? '24h'} onChange={v => set('knowledge_pipeline.crawl_interval', v)} options={[
            { value: '6h', label: t('cfgInterval6h') }, { value: '12h', label: t('cfgInterval12h') },
            { value: '24h', label: t('cfgInterval24h') }, { value: '7d', label: t('cfgInterval7d') },
          ]} />
        </Section>

        <Section title={t('cfgWebui')}>
          <Toggle label={t('cfgWebuiEnable')} desc={t('cfgWebuiEnableDesc')} value={config.webui?.enabled ?? false} onChange={v => set('webui.enabled', v)} />
          <div className="grid grid-cols-2 gap-4">
            <TextInput label={t('cfgWebuiHost')} value={config.webui?.host ?? '127.0.0.1'} onChange={v => set('webui.host', v)} placeholder="127.0.0.1" />
            <NumberInput label={t('cfgWebuiPort')} value={config.webui?.port ?? 8765} onChange={v => set('webui.port', v)} min={1024} max={65535} />
          </div>
        </Section>
      </div>

      <div className="sticky bottom-0 mt-6 -mx-6 px-6 py-4 border-t border-opc-border bg-opc-bg/95 backdrop-blur flex items-center justify-between">
        <span className="text-xs text-opc-text-2">{t('cfgSaveHint')}</span>
        <div className="flex items-center gap-3">
          {message && <span className={`text-xs ${message.startsWith('Error') ? 'text-red-400' : 'text-green-400'}`}>{message}</span>}
          <button onClick={save} className="btn-primary" disabled={saving}>{t('save')}</button>
        </div>
      </div>
    </div>
  )
}
