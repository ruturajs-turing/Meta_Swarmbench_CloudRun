import React, { useEffect, useMemo, useState } from 'react'
import { KeyRound, Plus, Search, Server, UserRoundCog } from 'lucide-react'
import { api } from '../api.js'
import { useNotice, usePolling } from '../hooks.js'
import { DetailList, Id, Inspector, Modal, Notice, PageHeader, Status, Table, Toolbar, formatDate } from '../ui.jsx'


const EMPTY_USER = { username: '', email: '', display_name: '', password: '', role: 'trainer' }


export function UsersPage({ onNavigate }) {
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [newUser, setNewUser] = useState(EMPTY_USER)
  const [quotaDraft, setQuotaDraft] = useState({})
  const [accountDraft, setAccountDraft] = useState({})
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const { notice, show, clear } = useNotice()
  const { data, loading, error, refresh } = usePolling(() => api.users({ q: search }), 5000, [search])
  const selected = useMemo(() => data?.users?.find((user) => user.id === selectedId), [data, selectedId])

  useEffect(() => {
    if (!selected) return
    setQuotaDraft(selected.quota || {})
    setAccountDraft({ display_name: selected.display_name, email: selected.email, role: selected.role, state: selected.state })
  }, [selected?.id, selected?.state])

  async function createUser() {
    setBusy(true)
    try {
      const created = await api.createUser(newUser)
      setCreateOpen(false)
      setNewUser(EMPTY_USER)
      setSelectedId(created.id)
      show(`Account @${created.username} created.`)
      await refresh()
    } catch (err) {
      show(err.message, 'danger')
    } finally { setBusy(false) }
  }

  async function saveAccount() {
    setBusy(true)
    try {
      await api.patchUser(selected.id, accountDraft)
      show('Account settings saved.')
      await refresh()
    } catch (err) { show(err.message, 'danger') } finally { setBusy(false) }
  }

  async function saveQuota() {
    const keys = ['max_active_runs', 'max_queued_runs', 'max_runtime_seconds', 'max_upload_mb', 'max_output_mb', 'max_monthly_cost', 'parent_cpu', 'parent_memory_mb', 'parent_disk_gb']
    const payload = Object.fromEntries(keys.map((key) => [key, quotaDraft[key] === '' || quotaDraft[key] === null ? null : Number(quotaDraft[key])]))
    setBusy(true)
    try {
      await api.updateQuota(selected.id, payload)
      show('Quota and parent capacity saved.')
      await refresh()
    } catch (err) { show(err.message, 'danger') } finally { setBusy(false) }
  }

  async function resetPassword() {
    setBusy(true)
    try {
      await api.resetPassword(selected.id, password)
      setPasswordOpen(false)
      setPassword('')
      show('Password reset. Existing sessions were revoked.')
    } catch (err) { show(err.message, 'danger') } finally { setBusy(false) }
  }

  async function createParent() {
    setBusy(true)
    try {
      const parent = await api.createParent(selected.id)
      sessionStorage.setItem('aegisrun_selected_parent', parent.id)
      show(parent.state === 'RUNNING' ? 'Parent workspace provisioned.' : `Parent provisioning ended in ${parent.state}.`, parent.state === 'RUNNING' ? 'success' : 'danger')
      await refresh()
      onNavigate('parents')
    } catch (err) { show(err.message, 'danger') } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Users and access" description="Issue trainer credentials, control account state, set run limits, and provision parent capacity." actions={<button className="button primary" onClick={() => setCreateOpen(true)}><Plus size={15} />Create user</button>} />
      {error && <div className="inline-alert danger">User inventory failed: {error}</div>}
      <Toolbar count={data?.users?.length}>
        <label className="search-field"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name, username, or email" /></label>
      </Toolbar>
      <div className={`ledger-layout ${selected ? 'with-inspector' : ''}`}>
        <Table columns={['User', 'Username', 'Role', 'Account', 'Parent', 'Active runs', 'Total runs', 'Last login']} empty={loading ? 'Loading users…' : 'No users match this search.'}>
          {(data?.users || []).map((user) => (
            <tr key={user.id} className={selectedId === user.id ? 'selected' : ''} onClick={() => setSelectedId(user.id)}>
              <td><strong>{user.display_name}</strong><small>{user.email}</small></td>
              <td className="mono">@{user.username}</td>
              <td>{user.role.replace('_', ' ')}</td>
              <td><Status value={user.state} /></td>
              <td><Status value={user.parent_state} /></td>
              <td>{user.active_runs} / {user.quota.max_active_runs}</td>
              <td>{user.run_count}</td>
              <td>{formatDate(user.last_login_at)}</td>
            </tr>
          ))}
        </Table>
        {selected && <Inspector title={selected.display_name} subtitle={`@${selected.username}`} status={<Status value={selected.state} />} onClose={() => setSelectedId(null)} actions={<><button className="button" onClick={() => setPasswordOpen(true)}><KeyRound size={14} />Reset password</button>{selected.role === 'trainer' && !selected.parent_id && <button className="button primary" onClick={createParent} disabled={busy}><Server size={14} />Create parent</button>}</>}>
          <section className="inspector-section"><h3>Identity</h3><DetailList items={[["User ID", <Id value={selected.id} copy />], ["Created", formatDate(selected.created_at)], ["Last login", formatDate(selected.last_login_at)], ["Parent", selected.parent_id ? <Id value={selected.parent_id} copy /> : 'Not created']]} /></section>
          <section className="inspector-section"><div className="section-title"><h3>Account settings</h3><UserRoundCog size={14} /></div><div className="form-grid">
            <label className="field">Display name<input value={accountDraft.display_name || ''} onChange={(event) => setAccountDraft({ ...accountDraft, display_name: event.target.value })} /></label>
            <label className="field">Email<input value={accountDraft.email || ''} onChange={(event) => setAccountDraft({ ...accountDraft, email: event.target.value })} /></label>
            <label className="field">Role<select value={accountDraft.role || 'trainer'} onChange={(event) => setAccountDraft({ ...accountDraft, role: event.target.value })}><option value="trainer">Trainer</option><option value="reviewer">Reviewer</option><option value="admin">Admin</option><option value="platform_admin">Platform admin</option></select></label>
            <label className="field">State<select value={accountDraft.state || 'active'} onChange={(event) => setAccountDraft({ ...accountDraft, state: event.target.value })}><option value="active">Active</option><option value="disabled">Disabled</option></select></label>
          </div><button className="button small" onClick={saveAccount} disabled={busy}>Save account</button></section>
          <section className="inspector-section"><h3>Child execution limits</h3><div className="form-grid three">
            {[['max_active_runs', 'Active runs'], ['max_queued_runs', 'Queued runs'], ['max_runtime_seconds', 'Runtime seconds'], ['max_upload_mb', 'Upload MB'], ['max_output_mb', 'Result MB'], ['max_monthly_cost', 'Monthly cost USD']].map(([key, label]) => <label className="field" key={key}>{label}<input type="number" value={quotaDraft[key] ?? ''} onChange={(event) => setQuotaDraft({ ...quotaDraft, [key]: event.target.value })} /></label>)}
          </div></section>
          <section className="inspector-section"><h3>Parent workspace capacity</h3><div className="form-grid three">
            {[['parent_cpu', 'CPU cores'], ['parent_memory_mb', 'Memory MB'], ['parent_disk_gb', 'Storage GB']].map(([key, label]) => <label className="field" key={key}>{label}<input type="number" value={quotaDraft[key] ?? ''} onChange={(event) => setQuotaDraft({ ...quotaDraft, [key]: event.target.value })} /></label>)}
          </div><button className="button small primary" onClick={saveQuota} disabled={busy}>Save limits</button></section>
        </Inspector>}
      </div>
      {createOpen && <Modal title="Create user account" description="These credentials work at the managed SSH endpoint. Trainer login provisions their parent workspace on first use." onClose={() => setCreateOpen(false)} actions={<><button className="button" onClick={() => setCreateOpen(false)}>Cancel</button><button className="button primary" onClick={createUser} disabled={busy || !newUser.username || !newUser.password}>{busy ? 'Creating…' : 'Create account'}</button></>}>
        <div className="form-grid"><label className="field">Display name<input value={newUser.display_name} onChange={(event) => setNewUser({ ...newUser, display_name: event.target.value })} /></label><label className="field">Username<input value={newUser.username} onChange={(event) => setNewUser({ ...newUser, username: event.target.value })} /></label><label className="field">Email<input value={newUser.email} onChange={(event) => setNewUser({ ...newUser, email: event.target.value })} /></label><label className="field">Role<select value={newUser.role} onChange={(event) => setNewUser({ ...newUser, role: event.target.value })}><option value="trainer">Trainer</option><option value="reviewer">Reviewer</option><option value="admin">Admin</option></select></label><label className="field full-span">Temporary password<input type="password" value={newUser.password} onChange={(event) => setNewUser({ ...newUser, password: event.target.value })} /></label></div>
      </Modal>}
      {passwordOpen && <Modal danger title={`Reset password for @${selected?.username}?`} description="All existing sessions for this account will be revoked." onClose={() => setPasswordOpen(false)} actions={<><button className="button" onClick={() => setPasswordOpen(false)}>Cancel</button><button className="button danger" disabled={password.length < 8 || busy} onClick={resetPassword}>{busy ? 'Resetting…' : 'Reset password'}</button></>}><label className="field">New password<input autoFocus type="password" value={password} onChange={(event) => setPassword(event.target.value)} /><small>At least 8 characters.</small></label></Modal>}
      <Notice notice={notice} onClose={clear} />
    </>
  )
}
