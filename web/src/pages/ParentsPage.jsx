import React, { useEffect, useMemo, useState } from 'react'
import { Box, Pause, Play, Plus, RefreshCcw, Search, Trash2 } from 'lucide-react'
import { api } from '../api.js'
import { useNotice, usePolling } from '../hooks.js'
import { DetailList, Id, Inspector, Modal, Notice, PageHeader, Status, Table, Toolbar, formatDate } from '../ui.jsx'


export function ParentsPage() {
  const [search, setSearch] = useState('')
  const [state, setState] = useState('ALL')
  const [selectedId, setSelectedId] = useState(() => sessionStorage.getItem('aegisrun_selected_parent'))
  const [createOpen, setCreateOpen] = useState(false)
  const [createUser, setCreateUser] = useState('')
  const [confirm, setConfirm] = useState(null)
  const [stats, setStats] = useState(null)
  const [busy, setBusy] = useState(false)
  const { notice, show, clear } = useNotice()
  const { data, loading, error, refresh } = usePolling(
    async () => {
      const [parents, users] = await Promise.all([api.parents({ q: search, state }), api.users()])
      return { parents: parents.parents, users: users.users }
    },
    3500,
    [search, state],
  )
  const selected = useMemo(() => data?.parents?.find((row) => row.id === selectedId), [data, selectedId])

  useEffect(() => {
    if (!selected) { setStats(null); return }
    api.parentStats(selected.id).then(setStats).catch((err) => setStats({ available: false, error: err.message }))
  }, [selected?.id, selected?.state])

  async function perform(action) {
    if (!selected) return
    setBusy(true)
    try {
      await api.parentAction(selected.id, action)
      show(`Parent workspace ${action} completed.`)
      setConfirm(null)
      await refresh()
    } catch (err) {
      show(err.message, 'danger')
    } finally {
      setBusy(false)
    }
  }

  async function create() {
    if (!createUser) return
    setBusy(true)
    try {
      const parent = await api.createParent(createUser)
      setSelectedId(parent.id)
      setCreateOpen(false)
      show(parent.state === 'RUNNING' ? 'Parent workspace provisioned.' : `Provisioning ended in ${parent.state}.`, parent.state === 'RUNNING' ? 'success' : 'danger')
      await refresh()
    } catch (err) {
      show(err.message, 'danger')
    } finally {
      setBusy(false)
    }
  }

  const availableUsers = (data?.users || []).filter((user) => user.role === 'trainer' && !user.parent_id)
  return (
    <>
      <PageHeader title="Parent workspaces" description="Provision and operate the persistent Harbor/OpenCode workspace owned by each trainer." actions={<button className="button primary" onClick={() => setCreateOpen(true)}><Plus size={15} />Create workspace</button>} />
      {error && <div className="inline-alert danger">Workspace inventory failed: {error}</div>}
      <Toolbar count={data?.parents?.length}>
        <label className="search-field"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="User, parent, or container ID" /></label>
        <select value={state} onChange={(event) => setState(event.target.value)}><option value="ALL">All states</option><option>RUNNING</option><option>PAUSED</option><option>PROVISIONING</option><option>REFRESHING</option><option>ERROR</option><option>DESTROYED</option></select>
        <button className="button small" onClick={() => refresh()}><RefreshCcw size={13} />Refresh</button>
      </Toolbar>
      <div className={`ledger-layout ${selected ? 'with-inspector' : ''}`}>
        <Table columns={['Owner', 'Parent ID', 'Container', 'State', 'Resources', 'Active children', 'Last active', '']} empty={loading ? 'Loading workspaces…' : 'No workspaces match these filters.'}>
          {(data?.parents || []).map((parent) => (
            <tr key={parent.id} className={selectedId === parent.id ? 'selected' : ''} onClick={() => { setSelectedId(parent.id); sessionStorage.setItem('aegisrun_selected_parent', parent.id) }}>
              <td><strong>{parent.display_name}</strong><small>@{parent.username}</small></td>
              <td><Id value={parent.id} /></td>
              <td><Id value={parent.container_id} /></td>
              <td><Status value={parent.state} /></td>
              <td>{parent.cpu} CPU · {Math.round(parent.memory_mb / 1024)} GB</td>
              <td>{parent.active_runs} / 2</td>
              <td>{formatDate(parent.last_active_at)}</td>
              <td><button className="row-open" title="Open workspace inspector"><Box size={14} /></button></td>
            </tr>
          ))}
        </Table>
        {selected && (
          <Inspector title={selected.display_name} subtitle={selected.id} status={<Status value={selected.state} />} onClose={() => setSelectedId(null)} actions={
            <>
              {selected.state === 'PAUSED' ? <button className="button primary" onClick={() => perform('resume')} disabled={busy}><Play size={14} />Resume</button> : <button className="button" onClick={() => perform('pause')} disabled={busy || selected.state !== 'RUNNING'}><Pause size={14} />Pause</button>}
              <button className="button" onClick={() => setConfirm('refresh')} disabled={busy}><RefreshCcw size={14} />Refresh image</button>
              <button className="button danger" onClick={() => setConfirm('destroy')} disabled={busy}><Trash2 size={14} />Destroy</button>
            </>
          }>
            {selected.error && <div className="inline-alert danger">{selected.error}</div>}
            <section className="inspector-section"><h3>Ownership</h3><DetailList items={[["Trainer", `@${selected.username}`], ["User ID", <Id value={selected.user_id} copy />], ["Provider", selected.provider], ["Template", selected.template_version]]} /></section>
            <section className="inspector-section"><h3>Allocated capacity</h3><DetailList items={[["CPU", `${selected.cpu} vCPU`], ["Memory", `${Math.round(selected.memory_mb / 1024)} GB`], ["Storage policy", `${selected.disk_gb} GB`], ["Tasks staged", selected.task_count]]} /></section>
            <section className="inspector-section"><h3>Live telemetry</h3><DetailList items={[["Provider state", stats?.state || '-'], ["CPU now", stats?.available ? `${stats.cpu_percent}%` : '-'], ["Memory now", stats?.available ? `${Math.round(stats.memory_used_bytes / 1048576)} MB` : '-'], ["Processes", stats?.pids ?? '-']]} /></section>
            <section className="inspector-section"><h3>Lifecycle</h3><DetailList items={[["Created", formatDate(selected.created_at)], ["Started", formatDate(selected.started_at)], ["Last active", formatDate(selected.last_active_at)], ["Refresh due", formatDate(selected.refresh_after_at)], ["Active child runs", selected.active_runs]]} /></section>
            <section className="inspector-section"><h3>Mounted workspace</h3><code className="path-block">{selected.workspace_uri}</code></section>
          </Inspector>
        )}
      </div>
      {createOpen && <Modal title="Create parent workspace" description="Provision the maintained Harbor/OpenCode image for one trainer." onClose={() => setCreateOpen(false)} actions={<><button className="button" onClick={() => setCreateOpen(false)}>Cancel</button><button className="button primary" onClick={create} disabled={!createUser || busy}>{busy ? 'Provisioning…' : 'Create workspace'}</button></>}>
        <label className="field">Trainer<select value={createUser} onChange={(event) => setCreateUser(event.target.value)}><option value="">Select a trainer</option>{availableUsers.map((user) => <option key={user.id} value={user.id}>{user.display_name} (@{user.username})</option>)}</select></label>
        {!availableUsers.length && <div className="inline-alert">Every trainer already has a parent workspace.</div>}
        <div className="provision-summary"><span>Image<strong>aegisrun/harbor-runner:local</strong></span><span>Default capacity<strong>2 CPU · 6 GB · 25 GB policy</strong></span><span>Lifecycle<strong>Pause at 15m idle · refresh at 24h</strong></span></div>
      </Modal>}
      {confirm && <Modal danger title={`${confirm === 'destroy' ? 'Destroy' : 'Refresh'} this parent workspace?`} description={confirm === 'destroy' ? 'The container will be removed. Stored tasks and completed result packages remain on durable storage.' : 'The container will be recreated from the latest managed image. Active child runs block this action.'} onClose={() => setConfirm(null)} actions={<><button className="button" onClick={() => setConfirm(null)}>Cancel</button><button className={`button ${confirm === 'destroy' ? 'danger' : 'primary'}`} onClick={() => perform(confirm)} disabled={busy}>{busy ? 'Working…' : confirm === 'destroy' ? 'Destroy workspace' : 'Refresh image'}</button></>}><p className="confirmation-id">Parent <Id value={selected?.id} copy /></p></Modal>}
      <Notice notice={notice} onClose={clear} />
    </>
  )
}
