import { useState, useEffect } from 'react'
import { api } from '../lib/api'

export default function Config() {
  const [config, setConfig] = useState<any>(null)
  const [edited, setEdited] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.getConfig().then(d => {
      setConfig(d.config)
      setEdited(JSON.stringify(d.config, null, 2))
    }).finally(() => setLoading(false))
  }, [])

  const save = () => {
    try {
      const parsed = JSON.parse(edited)
      setSaving(true)
      api.updateConfig(parsed).then(() => {
        setMessage('Saved!')
        setTimeout(() => setMessage(''), 2000)
      }).catch(e => setMessage(`Error: ${e.message}`))
      .finally(() => setSaving(false))
    } catch {
      setMessage('Invalid JSON')
    }
  }

  if (loading) return <div className="card animate-pulse"><div className="h-96 bg-opc-surface-2 rounded" /></div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">Configuration</h2>
        <div className="flex items-center gap-3">
          {message && <span className={`text-xs ${message.startsWith('Error') ? 'text-red-400' : 'text-green-400'}`}>{message}</span>}
          <button onClick={save} className="btn-primary text-xs" disabled={saving}>Save</button>
        </div>
      </div>

      <div className="card">
        <textarea
          className="w-full h-96 bg-opc-bg text-opc-text text-sm font-mono p-4 rounded-lg border border-opc-border focus:outline-none focus:border-opc-accent/50 resize-none"
          value={edited}
          onChange={e => setEdited(e.target.value)}
          spellCheck={false}
        />
      </div>
    </div>
  )
}
