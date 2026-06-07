import { useState } from 'react'
import { api } from '../lib/api'

export default function ArtifactViewer() {
  const [taskId, setTaskId] = useState('')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const lookup = () => {
    if (!taskId.trim()) return
    setLoading(true)
    setError(null)
    api.listArtifacts(taskId.trim())
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Artifact Viewer</h2>

      <div className="flex gap-3 mb-6">
        <input
          className="input flex-1 max-w-md"
          placeholder="Enter task ID..."
          value={taskId}
          onChange={e => setTaskId(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && lookup()}
        />
        <button onClick={lookup} className="btn-primary" disabled={loading}>Lookup</button>
      </div>

      {error && <div className="card border-red-500/30 bg-red-500/5 mb-6"><p className="text-red-400 text-sm">{error}</p></div>}

      {loading && <div className="card animate-pulse"><div className="h-32 bg-opc-surface-2 rounded" /></div>}

      {data?.artifacts && Object.keys(data.artifacts).length > 0 ? (
        <div className="space-y-4">
          {Object.entries(data.artifacts).map(([workerId, versions]: [string, any]) => (
            <div key={workerId} className="card">
              <h3 className="text-sm font-semibold mb-3">{workerId}</h3>
              <div className="flex flex-wrap gap-2">
                {versions.map((v: any) => (
                  <span key={v.version} className="badge-info text-xs">
                    v{v.version.toString().padStart(3, '0')} · {v.original_name} · {(v.file_size / 1024).toFixed(1)}KB
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        !loading && <div className="py-16 text-center text-opc-text-2 text-sm">Enter a task ID to browse artifacts</div>
      )}
    </div>
  )
}
