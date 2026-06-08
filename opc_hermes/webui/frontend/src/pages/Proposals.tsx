import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

const statusTabs = [
  { key: 'pending', labelKey: 'pending' },
  { key: 'approved', labelKey: 'approved' },
  { key: 'applied', labelKey: 'applied' },
]

export default function Proposals() {
  const { t } = useI18n()
  const [status, setStatus] = useState('pending')
  const [proposals, setProposals] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const fetch = () => {
    setLoading(true)
    api.listProposals(status)
      .then(d => setProposals(d.proposals ?? []))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [status])

  const handleAction = (id: string, action: 'approve' | 'reject') => {
    setActionLoading(id)
    const fn = action === 'approve' ? api.approveProposal : api.rejectProposal
    fn(id).then(() => fetch()).finally(() => setActionLoading(null))
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">{t('optimizationProposals')}</h2>
        <button onClick={() => api.triggerOptimizerScan().then(fetch)} className="btn-secondary text-xs">
          {t('runScanNow')}
        </button>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 mb-6">
        {statusTabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setStatus(tab.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              status === tab.key ? 'bg-opc-accent text-white' : 'bg-opc-surface-2 text-opc-text-2 hover:text-opc-text'
            }`}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="card animate-pulse"><div className="h-20 bg-opc-surface-2 rounded" /></div>)}
        </div>
      ) : proposals.length > 0 ? (
        <div className="space-y-3">
          {proposals.map(p => (
            <div key={p.id} className="card">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium">{p.title}</span>
                    <span className={`badge-${p.risk === 'low' ? 'success' : p.risk === 'medium' ? 'warning' : 'error'} text-xs`}>{p.risk}</span>
                    <span className="badge-accent text-xs">{p.type}</span>
                  </div>
                  <p className="text-xs text-opc-text-2 mb-2">{p.description}</p>
                  <div className="flex gap-4 text-xs text-opc-text-2">
                    <span>Worker: {p.worker_id}</span>
                    <span>Created: {p.created_at?.slice(0, 10)}</span>
                    {p.evidence?.avg_quality && <span>{t('avgQuality')}: {(p.evidence.avg_quality * 100).toFixed(0)}%</span>}
                  </div>
                </div>
                {status === 'pending' && (
                  <div className="flex gap-2 ml-4">
                    <button onClick={() => handleAction(p.id, 'approve')} disabled={actionLoading === p.id} className="btn-primary text-xs">
                      {t('approve')}
                    </button>
                    <button onClick={() => handleAction(p.id, 'reject')} disabled={actionLoading === p.id} className="btn-danger text-xs">
                      {t('reject')}
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="py-16 text-center text-opc-text-2 text-sm">{t('noProposals')}</div>
      )}
    </div>
  )
}
