import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowRight, LockKeyhole, ShieldCheck, Terminal } from 'lucide-react'
import { api } from './api.js'
import { Shell } from './Shell.jsx'
import { OverviewPage } from './pages/OverviewPage.jsx'
import { ParentsPage } from './pages/ParentsPage.jsx'
import { RunsPage } from './pages/RunsPage.jsx'
import { UsersPage } from './pages/UsersPage.jsx'
import { RuntimePage } from './pages/RuntimePage.jsx'
import { AuditPage } from './pages/AuditPage.jsx'
import './styles.css'


function Login({ onLogin }) {
  const [identifier, setIdentifier] = useState('admin')
  const [password, setPassword] = useState('aegisrun')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const result = await api.login(identifier, password)
      if (!['admin', 'platform_admin'].includes(result.user.role)) {
        throw new Error('This console is restricted to platform operators. Trainers connect through SSH.')
      }
      api.setToken(result.token)
      onLogin(result.user)
    } catch (err) {
      api.clearToken()
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel">
        <div className="login-brand"><span><ShieldCheck size={21} /></span><div><strong>AegisRun</strong><small>Operator access</small></div></div>
        <div className="login-copy">
          <p>Control plane</p>
          <h1>Manage the workspace fleet and every execution beneath it.</h1>
          <div className="login-lineage"><span>Trainer</span><ArrowRight size={14} /><span>Parent workspace</span><ArrowRight size={14} /><span>Child run</span><ArrowRight size={14} /><span>Result</span></div>
        </div>
        <form onSubmit={submit}>
          <label>Username or email<input autoFocus value={identifier} onChange={(event) => setIdentifier(event.target.value)} /></label>
          <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {error && <div className="form-error">{error}</div>}
          <button className="button primary full" disabled={loading}><LockKeyhole size={15} />{loading ? 'Connecting…' : 'Open control plane'}</button>
        </form>
        <div className="trainer-note"><Terminal size={15} /><span>Trainer access stays separate at the managed SSH endpoint.</span></div>
      </section>
      <aside className="login-context">
        <span>What this console controls</span>
        <ul><li>Trainer accounts and quotas</li><li>Parent workspace lifecycle</li><li>Live child executions and logs</li><li>Result packages and cleanup</li><li>Runtime images and connectivity</li></ul>
      </aside>
    </main>
  )
}


function App() {
  const [user, setUser] = useState(null)
  const [section, setSection] = useState(() => window.location.hash.slice(1) || 'overview')
  const [checking, setChecking] = useState(api.hasToken())

  useEffect(() => {
    if (!api.hasToken()) return
    api.me().then((current) => {
      if (!['admin', 'platform_admin'].includes(current.role)) throw new Error('Not an operator')
      setUser(current)
    }).catch(() => api.clearToken()).finally(() => setChecking(false))
  }, [])

  function changeSection(next) {
    setSection(next)
    window.location.hash = next
  }

  async function logout() {
    try { await api.logout() } catch { /* local logout must still succeed */ }
    api.clearToken()
    setUser(null)
  }

  if (checking) return <div className="boot"><ShieldCheck size={24} /><span>Connecting to control plane…</span></div>
  if (!user) return <Login onLogin={setUser} />

  const pages = {
    overview: <OverviewPage onNavigate={changeSection} />,
    parents: <ParentsPage />,
    runs: <RunsPage />,
    users: <UsersPage onNavigate={changeSection} />,
    runtime: <RuntimePage />,
    audit: <AuditPage />,
  }
  return <Shell user={user} section={section} onSection={changeSection} onLogout={logout}>{pages[section] || pages.overview}</Shell>
}


createRoot(document.getElementById('root')).render(<App />)
