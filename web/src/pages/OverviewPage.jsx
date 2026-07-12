import React from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Boxes,
  CircleDollarSign,
  Cloud,
  Container,
  Database,
  Server,
  Users,
} from 'lucide-react'
import { api } from '../api.js'
import { usePolling } from '../hooks.js'
import { formatDate, formatDuration, Id, PageHeader, Status, Table } from '../ui.jsx'


function HealthCheck({ icon: Icon, label, ok, detail }) {
  return <div className={`health-check ${ok ? 'ok' : 'bad'}`}><Icon size={15} /><span><strong>{label}</strong><small>{detail}</small></span><b>{ok ? 'Connected' : 'Attention'}</b></div>
}


export function OverviewPage({ onNavigate }) {
  const { data, loading, error, refresh } = usePolling(async () => {
    const [overview, costs] = await Promise.all([api.overview(), api.costs()])
    return { ...overview, costs }
  }, 3500, [])

  const openRun = (run) => {
    sessionStorage.setItem('aegisrun_selected_run', run.id)
    onNavigate('runs')
  }
  const openParent = (parent) => {
    sessionStorage.setItem('aegisrun_selected_parent', parent.id)
    onNavigate('parents')
  }

  return (
    <>
      <PageHeader
        title="Fleet overview"
        description="Live ownership, execution state, and operator attention across the trainer fleet."
        actions={<button className="button" onClick={() => refresh()} disabled={loading}>Refresh now</button>}
      />
      {error && <div className="inline-alert danger">Control-plane refresh failed: {error}</div>}
      <section className="health-strip">
        <HealthCheck icon={Database} label="Control plane" ok={!error} detail={error ? 'API request failed' : 'API and Postgres responding'} />
        <HealthCheck icon={Container} label="Docker provider" ok={data?.runtime?.docker} detail={data?.runtime?.docker ? 'Lifecycle actions available' : data?.runtime?.error || 'Socket unavailable'} />
        <HealthCheck icon={Boxes} label="Parent image" ok={data?.runtime?.parent_image} detail={data?.runtime?.parent_image_name || 'Not configured'} />
        <HealthCheck icon={Cloud} label="Harbor + Fireworks" ok={data?.runtime?.harbor_enabled && data?.runtime?.fireworks_configured} detail={data?.runtime?.harbor_enabled ? (data?.runtime?.fireworks_configured ? 'Runtime and credential configured' : 'Credential missing') : 'Runtime disabled'} />
      </section>

      <section className="metric-ledger">
        <div><Users size={15} /><span>Trainer accounts</span><strong>{data?.counts?.users ?? '-'}</strong></div>
        <div><Server size={15} /><span>Parents running</span><strong>{data?.counts?.parents_running ?? '-'}</strong><small>{data?.counts?.parents_attention || 0} need attention</small></div>
        <div><Activity size={15} /><span>Child executions</span><strong>{data?.counts?.executions_active ?? '-'}</strong><small>{data?.counts?.runs_queued || 0} queued</small></div>
        <div><AlertTriangle size={15} /><span>Failed runs</span><strong>{data?.counts?.failures ?? '-'}</strong></div>
        <div><CircleDollarSign size={15} /><span>Recorded run cost</span><strong>${Number(data?.costs?.run_cost || 0).toFixed(4)}</strong><small>${Number(data?.costs?.active_parent_hourly_estimate || 0).toFixed(2)}/h parent estimate</small></div>
      </section>

      <section className="surface lineage-surface">
        <div className="surface-head"><div><h2>Live fleet lineage</h2><p>Every active resource remains attached to its owner and parent workspace.</p></div><span className="record-count">{data?.topology?.length || 0} trainer paths</span></div>
        <div className="topology-list">
          {(data?.topology || []).map((item) => (
            <div className="topology-row" key={item.user.id}>
              <button className="topology-node trainer" onClick={() => onNavigate('users')}>
                <small>Trainer</small><strong>{item.user.display_name}</strong><span>@{item.user.username}</span>
              </button>
              <ArrowRight size={17} />
              {item.parent ? (
                <button className="topology-node parent" onClick={() => openParent(item.parent)}>
                  <small>Parent workspace</small><strong><Status value={item.parent.state} /></strong><span><Id value={item.parent.id} /> · {item.parent.cpu} CPU / {Math.round(item.parent.memory_mb / 1024)} GB</span>
                </button>
              ) : <button className="topology-node missing" onClick={() => onNavigate('parents')}><small>Parent workspace</small><strong>Not created</strong><span>Provision from Workspaces</span></button>}
              <ArrowRight size={17} />
              <div className="execution-branch">
                {item.executions.length ? item.executions.map((run) => (
                  <button className="execution-node" key={run.id} onClick={() => openRun(run)}>
                    <Status value={run.state} /><strong>{run.task_name.replace('swarmbench/', '').slice(0, 42)}</strong><span><Id value={run.id} /> · {run.cpu} CPU / {Math.round(run.memory_mb / 1024)} GB</span>
                  </button>
                )) : <span className="idle-node">No active child executions</span>}
              </div>
            </div>
          ))}
          {!data?.topology?.length && <div className="empty-state">{loading ? 'Loading fleet lineage…' : 'No trainer accounts exist yet.'}</div>}
        </div>
      </section>

      <div className="overview-lower">
        <section className="surface">
          <div className="surface-head"><div><h2>Needs attention</h2><p>Terminal failures and infrastructure errors requiring review.</p></div><button className="text-button" onClick={() => onNavigate('runs')}>Open run ledger <ArrowRight size={13} /></button></div>
          <Table columns={['Run', 'Trainer', 'State', 'Task', 'When']} empty="No failed runs require attention.">
            {(data?.attention_runs || []).map((run) => (
              <tr key={run.id} onClick={() => openRun(run)}>
                <td><Id value={run.id} /></td><td>@{run.username}</td><td><Status value={run.state} /></td><td className="truncate">{run.task_name}</td><td>{formatDate(run.finished_at || run.queued_at)}</td>
              </tr>
            ))}
          </Table>
        </section>
        <section className="surface">
          <div className="surface-head"><div><h2>Recent execution ledger</h2><p>Latest child runs across all trainers.</p></div></div>
          <Table columns={['Run', 'Trainer', 'Result', 'Elapsed', 'Cost']}>
            {(data?.recent_runs || []).slice(0, 8).map((run) => (
              <tr key={run.id} onClick={() => openRun(run)}>
                <td><Id value={run.id} /></td><td>@{run.username}</td><td><Status value={run.passed === true ? 'PASSED' : run.passed === false ? 'FAILED' : run.state} /></td><td>{formatDuration(run.duration_seconds)}</td><td>${Number(run.cost_estimate || 0).toFixed(4)}</td>
              </tr>
            ))}
          </Table>
        </section>
      </div>
    </>
  )
}
