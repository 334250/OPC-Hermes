import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

export default function TaskList() {
  const { t } = useI18n()
  const [tasks, setTasks] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTasks()
  }, [])

  const fetchTasks = () => {
    setLoading(true)
    setError(null)
    api.listTasks()
      .then(d => setTasks(d.tasks ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">{t('tasks')}</h2>

      {error && (
        <div className="card border-red-500/30 bg-red-500/5 mb-6">
          <p className="text-red-400 text-sm">{error}</p>
          <button onClick={fetchTasks} className="btn-primary mt-3 text-xs">{t('retry')}</button>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="card animate-pulse">
              <div className="h-5 w-48 bg-opc-surface-2 rounded mb-2" />
              <div className="h-3 w-64 bg-opc-surface-2 rounded opacity-50" />
            </div>
          ))}
        </div>
      ) : tasks.length > 0 ? (
        <div className="space-y-3">
          {tasks.map((task: any) => (
            <Link to={`/tasks/${task.task_id}`} key={task.task_id} className="card block group">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-opc-text group-hover:text-opc-accent transition-colors">
                    {task.task_id}
                  </div>
                  <div className="text-xs text-opc-text-2 mt-1">
                    {task.total_steps} {t('steps')} · {task.workers?.join(', ')}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-opc-text-2">{task.last_activity?.slice(0, 10)}</span>
                  <span className={`badge-${task.status === 'completed' ? 'success' : task.status === 'partial' ? 'warning' : 'info'} text-xs`}>
                    {task.status}
                  </span>
                  <span className="text-opc-text-2 text-sm">→</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="py-16 text-center text-opc-text-2 text-sm">
          {t('noTasksFound')}
        </div>
      )}
    </div>
  )
}
