import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import AgentList from './pages/AgentList'
import AgentDetail from './pages/AgentDetail'
import TaskList from './pages/TaskList'
import TaskDetail from './pages/TaskDetail'
import MemoryBrowser from './pages/MemoryBrowser'
import ArtifactViewer from './pages/ArtifactViewer'
import Proposals from './pages/Proposals'
import Config from './pages/Config'
import HermesChat from './pages/HermesChat'
import HermesPanel from './pages/HermesPanel'
import {
  HermesConfigPage,
  HermesCronPage,
  HermesKeysPage,
  HermesLogsPage,
  HermesModelsPage,
  HermesPluginsPage,
  HermesSessionsPage,
  HermesSkillsPage,
} from './pages/NativeHermes'
import { useI18n } from './lib/i18n'

const navItems = [
  { to: '/', labelKey: 'opcDashboard', icon: '◈' },
  { to: '/chat', labelKey: 'chat', icon: '▣' },
  { to: '/sessions', labelKey: 'sessions', icon: '◫' },
  { to: '/analytics', labelKey: 'analytics', icon: '▥' },
  { to: '/models', labelKey: 'models', icon: '◉' },
  { to: '/logs', labelKey: 'logs', icon: '▤' },
  { to: '/cron', labelKey: 'cron', icon: '◷' },
  { to: '/skills', labelKey: 'skills', icon: '▧' },
  { to: '/plugins', labelKey: 'plugins', icon: '✣' },
  { to: '/profiles', labelKey: 'profiles', icon: '♙' },
  { to: '/config', labelKey: 'config', icon: '⚙' },
  { to: '/env', labelKey: 'keys', icon: '⚿' },
  { to: '/documentation', labelKey: 'documentation', icon: '▨' },
  { to: '/tasks', labelKey: 'taskList', icon: '▦' },
  { to: '/tasks/new', labelKey: 'createTask', icon: '+' },
  { to: '/agents', labelKey: 'agentManager', icon: '⎔' },
  { to: '/memory', labelKey: 'memoryBrowser', icon: '▤' },
  { to: '/artifacts', labelKey: 'artifactViewer', icon: '⬡' },
  { to: '/proposals', labelKey: 'proposalReview', icon: '✦' },
  { to: '/opc-config', labelKey: 'opcConfig', icon: '☷' },
]

export default function App() {
  const { lang, setLang, t } = useI18n()

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 bg-opc-surface border-r border-opc-border flex flex-col">
        <div className="p-5 border-b border-opc-border">
          <h1 className="text-lg font-semibold tracking-tight text-opc-accent">OPC-Hermes</h1>
          <p className="text-xs text-opc-text-2 mt-1">{t('appSubtitle')}</p>
        </div>
        <nav className="flex-1 overflow-auto p-3">
          <div className="space-y-1">
          {navItems.map(({ to, labelKey, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-opc-accent/10 text-opc-accent border-l-2 border-opc-accent'
                    : 'text-opc-text-2 hover:text-opc-text hover:bg-opc-surface-2'
                }`
              }
            >
              <span className="text-base">{icon}</span>
              {t(labelKey)}
            </NavLink>
          ))}
          </div>
        </nav>
        <div className="p-4 border-t border-opc-border text-xs text-opc-text-2">
          v0.1.0 · OPC-Hermes
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        <header className="sticky top-0 z-10 border-b border-opc-border bg-opc-bg/95 backdrop-blur">
          <div className="flex h-14 items-center justify-between px-6">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-opc-text">OPC · Hermes</span>
              <span className="badge-info text-xs">{t('workerStatus')}</span>
            </div>
            <div className="flex items-center gap-2">
              <a className="btn-secondary text-xs" href="/docs" target="_blank" rel="noreferrer">{t('apiDocs')}</a>
              <a className="btn-secondary text-xs" href="/api/health" target="_blank" rel="noreferrer">{t('health')}</a>
              <div className="flex rounded-lg border border-opc-border bg-opc-surface-2 p-0.5">
                <button
                  onClick={() => setLang('zh')}
                  className={`px-2.5 py-1 rounded-md text-xs ${lang === 'zh' ? 'bg-opc-accent text-white' : 'text-opc-text-2 hover:text-opc-text'}`}
                  title={t('chinese')}
                >
                  中
                </button>
                <button
                  onClick={() => setLang('en')}
                  className={`px-2.5 py-1 rounded-md text-xs ${lang === 'en' ? 'bg-opc-accent text-white' : 'text-opc-text-2 hover:text-opc-text'}`}
                  title={t('english')}
                >
                  EN
                </button>
              </div>
            </div>
          </div>
        </header>
        <div className="p-6 max-w-7xl mx-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<HermesChat />} />
            <Route path="/sessions" element={<HermesSessionsPage />} />
            <Route path="/analytics" element={<HermesPanel />} />
            <Route path="/models" element={<HermesModelsPage />} />
            <Route path="/logs" element={<HermesLogsPage />} />
            <Route path="/cron" element={<HermesCronPage />} />
            <Route path="/skills" element={<HermesSkillsPage />} />
            <Route path="/plugins" element={<HermesPluginsPage />} />
            <Route path="/profiles" element={<HermesPanel />} />
            <Route path="/config" element={<HermesConfigPage />} />
            <Route path="/env" element={<HermesKeysPage />} />
            <Route path="/documentation" element={<HermesPanel />} />
            <Route path="/agents" element={<AgentList />} />
            <Route path="/agents/:agentId" element={<AgentDetail />} />
            <Route path="/tasks" element={<TaskList />} />
            <Route path="/tasks/new" element={<TaskDetail />} />
            <Route path="/tasks/:taskId" element={<TaskDetail />} />
            <Route path="/memory" element={<MemoryBrowser />} />
            <Route path="/artifacts" element={<ArtifactViewer />} />
            <Route path="/artifacts/:taskId" element={<ArtifactViewer />} />
            <Route path="/proposals" element={<Proposals />} />
            <Route path="/opc-config" element={<Config />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}
