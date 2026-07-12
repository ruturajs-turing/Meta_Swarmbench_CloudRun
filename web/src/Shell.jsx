import React, { useEffect, useState } from 'react'
import {
  Activity,
  Boxes,
  CircleGauge,
  ClipboardList,
  CloudCog,
  LogOut,
  RefreshCcw,
  ShieldCheck,
  Terminal,
  Users,
} from 'lucide-react'
import { api } from './api.js'

const NAV = [
  ['overview', CircleGauge, 'Overview'],
  ['parents', Boxes, 'Workspaces'],
  ['runs', Activity, 'Runs'],
  ['users', Users, 'Users'],
  ['runtime', CloudCog, 'Runtime'],
  ['audit', ClipboardList, 'Audit'],
]

export function Shell({ user, section, onSection, onLogout, children }) {
  const [runtime, setRuntime] = useState(null)
  const [terminal, setTerminal] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  async function load() {
    setRefreshing(true)
    try {
      const [providerData, terminalData] = await Promise.all([api.providers(), api.terminal()])
      setRuntime(providerData.runtime)
      setTerminal(terminalData)
    } catch {
      setRuntime({ docker: false })
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 10000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="admin-shell">
      <header className="app-bar">
        <button className="brand" onClick={() => onSection('overview')}>
          <span className="brand-mark"><ShieldCheck size={18} /></span>
          <span><strong>AegisRun</strong><small>Control plane</small></span>
        </button>
        <nav className="primary-nav">
          {NAV.map(([id, Icon, label]) => (
            <button key={id} className={section === id ? 'active' : ''} onClick={() => onSection(id)}>
              <Icon size={15} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="app-bar-spacer" />
        <button className="connection" onClick={load} title="Refresh provider connectivity">
          <span className={`live-dot ${runtime?.docker ? 'healthy' : 'down'}`} />
          <span>{runtime?.docker ? 'Docker connected' : 'Provider offline'}</span>
          <RefreshCcw size={13} className={refreshing ? 'spin' : ''} />
        </button>
        <button className="terminal-link" onClick={() => onSection('runtime')} title={terminal?.ssh_command || 'Terminal endpoint'}>
          <Terminal size={14} /> SSH :{terminal?.ssh_port || 2222}
        </button>
        <div className="account">
          <span className="avatar">{user.display_name.split(' ').map((item) => item[0]).join('').slice(0, 2)}</span>
          <span><strong>{user.display_name}</strong><small>{user.role.replace('_', ' ')}</small></span>
          <button className="icon-button" onClick={onLogout} title="Sign out"><LogOut size={16} /></button>
        </div>
      </header>
      <main className="workspace">{children}</main>
    </div>
  )
}
