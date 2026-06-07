import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import AgentList from './pages/AgentList'
import AgentDetail from './pages/AgentDetail'
import TaskDetail from './pages/TaskDetail'
import MemoryBrowser from './pages/MemoryBrowser'
import ArtifactViewer from './pages/ArtifactViewer'
import Proposals from './pages/Proposals'
import Config from './pages/Config'

const navItems = [
  { to: '/', label: 'Dashboard', icon: '◈' },
  { to: '/agents', label: 'Agents', icon: '⎔' },
  { to: '/memory', label: 'Memory', icon: '▤' },
  { to: '/artifacts', label: 'Artifacts', icon: '⬡' },
  { to: '/proposals', label: 'Proposals', icon: '✦' },
  { to: '/config', label: 'Config', icon: '⚙' },
]

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 bg-opc-surface border-r border-opc-border flex flex-col">
        <div className="p-5 border-b border-opc-border">
          <h1 className="text-lg font-semibold tracking-tight text-opc-accent">OPC-Hermes</h1>
          <p className="text-xs text-opc-text-2 mt-1">Multi-Agent Dashboard</p>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(({ to, label, icon }) => (
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
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-opc-border text-xs text-opc-text-2">
          v0.1.0 · OPC-Hermes
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6 max-w-7xl mx-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/agents" element={<AgentList />} />
            <Route path="/agents/:agentId" element={<AgentDetail />} />
            <Route path="/tasks/:taskId" element={<TaskDetail />} />
            <Route path="/memory" element={<MemoryBrowser />} />
            <Route path="/artifacts" element={<ArtifactViewer />} />
            <Route path="/artifacts/:taskId" element={<ArtifactViewer />} />
            <Route path="/proposals" element={<Proposals />} />
            <Route path="/config" element={<Config />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}
