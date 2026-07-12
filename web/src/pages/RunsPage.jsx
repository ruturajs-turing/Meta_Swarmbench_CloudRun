import React, { useEffect, useMemo, useState } from 'react'
import { Archive, Download, RefreshCcw, RotateCcw, Search, Square } from 'lucide-react'
import { api } from '../api.js'
import { useNotice, usePolling } from '../hooks.js'
import {
  ACTIVE_STATES,
  ArtifactButton,
  DetailList,
  Id,
  Inspector,
  Lineage,
  Modal,
  Notice,
  PageHeader,
  Status,
  Table,
  Toolbar,
  formatDate,
  formatDuration,
} from '../ui.jsx'


const STATES = ['ALL', 'QUEUED', 'PROVISIONING', 'STAGING_INPUTS', 'RUNNING', 'COLLECTING_OUTPUTS', 'FINALIZING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT', 'CANCELLED', 'INFRA_FAILED']


export function RunsPage() {
  const [search, setSearch] = useState('')
  const [state, setState] = useState('ALL')
  const [userId, setUserId] = useState('')
  const [selectedId, setSelectedId] = useState(() => sessionStorage.getItem('aegisrun_selected_run'))
  const [evidence, setEvidence] = useState({ events: [], artifacts: [] })
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const { notice, show, clear } = useNotice()
  const { data, loading, error, refresh } = usePolling(
    async () => {
      const [runs, users] = await Promise.all([api.runs({ q: search, state, user_id: userId }), api.users()])
      return { runs: runs.runs, users: users.users }
    },
    3000,
    [search, state, userId],
  )
  const selected = useMemo(() => data?.runs?.find((run) => run.id === selectedId), [data, selectedId])

  useEffect(() => {
    if (!selectedId) { setEvidence({ events: [], artifacts: [] }); return }
    let active = true
    async function load() {
      try {
        const [events, artifacts] = await Promise.all([api.events(selectedId), api.artifacts(selectedId)])
        if (active) setEvidence({ events: events.events, artifacts: artifacts.artifacts })
      } catch { /* selected record may have been replaced by a filter */ }
    }
    load()
    const timer = setInterval(load, 1800)
    return () => { active = false; clearInterval(timer) }
  }, [selectedId])

  async function perform(action) {
    if (!selected) return
    setBusy(true)
    try {
      if (action === 'stop') await api.cancelRun(selected.id)
      if (action === 'retry') {
        const retried = await api.retryRun(selected.id)
        setSelectedId(retried.id)
      }
      if (action === 'cleanup') await api.forceCleanup(selected.id)
      show(action === 'retry' ? 'Retry queued.' : action === 'stop' ? 'Cancellation requested.' : 'Cleanup reconciled.')
      setConfirm(null)
      await refresh()
    } catch (err) {
      show(err.message, 'danger')
    } finally {
      setBusy(false)
    }
  }

  function select(run) {
    setSelectedId(run.id)
    sessionStorage.setItem('aegisrun_selected_run', run.id)
  }

  return (
    <>
      <PageHeader title="Execution runs" description="Observe, stop, retry, inspect, and clean every ephemeral child sandbox from one ledger." actions={<button className="button" onClick={() => refresh()}><RefreshCcw size={14} />Refresh now</button>} />
      {error && <div className="inline-alert danger">Run inventory failed: {error}</div>}
      <Toolbar count={data?.runs?.length}>
        <label className="search-field"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Run, task, parent, or container ID" /></label>
        <select value={state} onChange={(event) => setState(event.target.value)}>{STATES.map((item) => <option key={item}>{item === 'ALL' ? 'All states' : item.replaceAll('_', ' ')}</option>)}</select>
        <select value={userId} onChange={(event) => setUserId(event.target.value)}><option value="">All trainers</option>{(data?.users || []).filter((user) => user.role === 'trainer').map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select>
      </Toolbar>
      <div className={`ledger-layout ${selected ? 'with-inspector' : ''}`}>
        <Table columns={['Run ID', 'Trainer', 'Task', 'State', 'Child', 'Resources', 'Elapsed', 'Result', 'Cost']} empty={loading ? 'Loading runs…' : 'No runs match these filters.'}>
          {(data?.runs || []).map((run) => (
            <tr key={run.id} className={selectedId === run.id ? 'selected' : ''} onClick={() => select(run)}>
              <td><Id value={run.id} /></td>
              <td><strong>{run.display_name}</strong><small>@{run.username}</small></td>
              <td className="truncate" title={run.task_name}>{run.task_name}</td>
              <td><Status value={run.state} /></td>
              <td><Id value={run.container_id} /></td>
              <td>{run.cpu} CPU · {Math.round(run.memory_mb / 1024)} GB</td>
              <td>{formatDuration(run.duration_seconds)}</td>
              <td><Status value={run.passed === true ? 'PASSED' : run.passed === false ? 'FAILED' : 'PENDING'} /></td>
              <td>${Number(run.cost_estimate || 0).toFixed(4)}</td>
            </tr>
          ))}
        </Table>
        {selected && <Inspector title={selected.task_name.replace('swarmbench/', '')} subtitle={selected.id} status={<Status value={selected.state} />} onClose={() => setSelectedId(null)} actions={
          <>
            {ACTIVE_STATES.includes(selected.state) ? <button className="button danger" onClick={() => setConfirm('stop')}><Square size={14} />Stop run</button> : <button className="button primary" onClick={() => setConfirm('retry')}><RotateCcw size={14} />Retry</button>}
            <button className="button" onClick={() => setConfirm('cleanup')}><Archive size={14} />Force cleanup</button>
          </>
        }>
          <section className="inspector-section"><h3>Resource lineage</h3><Lineage run={selected} /></section>
          {selected.failure_reason && <div className="inline-alert danger"><strong>Failure</strong>{selected.failure_reason}</div>}
          <section className="inspector-section"><h3>Execution</h3><DetailList items={[["Mode", selected.execution_mode], ["Provider", selected.provider], ["Child container", <Id value={selected.container_id} copy />], ["Resources", `${selected.cpu} CPU / ${selected.memory_mb} MB / ${selected.disk_gb} GB`], ["Queued", formatDate(selected.queued_at)], ["Started", formatDate(selected.started_at)], ["Finished", formatDate(selected.finished_at)], ["Elapsed", formatDuration(selected.duration_seconds)], ["Exit code", selected.exit_code], ["Cleanup", selected.cleanup_state], ["Estimated cost", `$${Number(selected.cost_estimate || 0).toFixed(4)}`]]} /></section>
          <section className="inspector-section"><div className="section-title"><h3>Result packages</h3><span>{evidence.artifacts.length}</span></div>{evidence.artifacts.length ? evidence.artifacts.map((artifact) => <ArtifactButton key={artifact.id} artifact={artifact} onDownload={() => api.downloadArtifact(selected.id, artifact.id, artifact.path).catch((err) => show(err.message, 'danger'))} />) : <p className="muted">Result collection has not produced a package yet.</p>}</section>
          <section className="inspector-section"><div className="section-title"><h3>Live event timeline</h3><span>{evidence.events.length}</span></div><div className="event-timeline">{evidence.events.map((event) => <div key={event.sequence_number} className={event.type === 'LOG' ? 'log-event' : ''}><i>{String(event.sequence_number).padStart(3, '0')}</i><span><strong>{event.type.replaceAll('_', ' ')}</strong><small>{event.message}</small></span><time>{formatDate(event.ts)}</time></div>)}{!evidence.events.length && <p className="muted">Waiting for the first run event.</p>}</div></section>
          <section className="inspector-section"><div className="section-title"><h3>Model log output</h3><Download size={13} /></div><pre className="run-log">{evidence.events.filter((event) => event.type === 'LOG').map((event) => event.message).join('\n') || 'No stdout has been recorded.'}</pre></section>
        </Inspector>}
      </div>
      {confirm && <Modal danger={confirm === 'stop' || confirm === 'cleanup'} title={confirm === 'stop' ? 'Stop this child execution?' : confirm === 'retry' ? 'Retry this run?' : 'Force cleanup for this run?'} description={confirm === 'stop' ? 'The child container will be killed. Logs collected so far remain available.' : confirm === 'retry' ? 'A new child run will be queued with the same task bundle, resources, and mode.' : 'Any remaining child container will be destroyed and cleanup state reconciled.'} onClose={() => setConfirm(null)} actions={<><button className="button" onClick={() => setConfirm(null)}>Cancel</button><button className={`button ${confirm === 'retry' ? 'primary' : 'danger'}`} onClick={() => perform(confirm)} disabled={busy}>{busy ? 'Working…' : confirm === 'stop' ? 'Stop execution' : confirm === 'retry' ? 'Queue retry' : 'Force cleanup'}</button></>}><p className="confirmation-id">Run <Id value={selected?.id} copy /></p></Modal>}
      <Notice notice={notice} onClose={clear} />
    </>
  )
}
