import React, { useState } from 'react'
import { Boxes, CheckCircle2, CircleDollarSign, Cloud, Container, Copy, Play, RefreshCcw, Server, Terminal, XCircle } from 'lucide-react'
import { api } from '../api.js'
import { useNotice, usePolling } from '../hooks.js'
import { Notice, PageHeader, Status } from '../ui.jsx'


function RuntimeCheck({ icon: Icon, label, state, detail }) {
  return <div className="runtime-check"><Icon size={18} /><span><small>{label}</small><strong>{state ? 'Ready' : 'Not ready'}</strong><p>{detail}</p></span>{state ? <CheckCircle2 size={17} className="ok-text" /> : <XCircle size={17} className="danger-text" />}</div>
}


export function RuntimePage() {
  const [busy, setBusy] = useState(false)
  const { notice, show, clear } = useNotice()
  const { data, loading, error, refresh } = usePolling(async () => {
    const [providers, terminal, costs] = await Promise.all([api.providers(), api.terminal(), api.costs()])
    return { ...providers, terminal, costs }
  }, 8000, [])
  const runtime = data?.runtime || {}

  async function reconcile() {
    setBusy(true)
    try {
      const result = await api.reconcile()
      show(`Reconciled: ${result.execution_containers_destroyed} child container(s) destroyed, ${result.paused} parent(s) paused, ${result.refreshed} refreshed.`)
      await refresh()
    } catch (err) { show(err.message, 'danger') } finally { setBusy(false) }
  }

  function copy(value) {
    navigator.clipboard.writeText(value)
    show('Command copied.')
  }

  return (
    <>
      <PageHeader title="Runtime and access" description="Provider connectivity, managed images, terminal endpoint, lifecycle policy, and current cost posture." actions={<button className="button primary" onClick={reconcile} disabled={busy || loading}><RefreshCcw size={14} />{busy ? 'Reconciling…' : 'Run reconciler'}</button>} />
      {error && <div className="inline-alert danger">Runtime health failed: {error}</div>}
      <section className="runtime-grid">
        <RuntimeCheck icon={Container} label="Local Docker provider" state={runtime.docker} detail={runtime.docker ? 'Parent and child lifecycle operations are available.' : runtime.error || 'Docker socket is unavailable.'} />
        <RuntimeCheck icon={Boxes} label="Parent workspace image" state={runtime.parent_image} detail={runtime.parent_image_name || 'No parent image configured.'} />
        <RuntimeCheck icon={Play} label="Harbor runner image" state={runtime.runner_image && runtime.harbor_enabled} detail={runtime.runner_image_name || 'No runner image configured.'} />
        <RuntimeCheck icon={Cloud} label="Fireworks credential" state={runtime.fireworks_configured} detail={runtime.fireworks_configured ? 'Credential is present in the control plane and injected only into child runs.' : 'Set FIREWORKS_API_KEY before enabling Harbor runs.'} />
      </section>

      <div className="runtime-columns">
        <section className="surface">
          <div className="surface-head"><div><h2>Trainer terminal endpoint</h2><p>Operators create the account; trainers authenticate here with the issued username and password.</p></div><Terminal size={18} /></div>
          <div className="command-list">
            <button onClick={() => copy(data?.terminal?.ssh_command || '')}><span><small>Interactive terminal</small><code>{data?.terminal?.ssh_command || 'Loading…'}</code></span><Copy size={14} /></button>
            <button onClick={() => copy(data?.terminal?.sftp_command || '')}><span><small>Task upload and result download</small><code>{data?.terminal?.sftp_command || 'Loading…'}</code></span><Copy size={14} /></button>
          </div>
          <ol className="operator-flow"><li><span>1</span><div><strong>Issue credentials</strong><p>Create a trainer account in Users.</p></div></li><li><span>2</span><div><strong>Trainer logs in</strong><p>Login provisions or resumes their parent workspace.</p></div></li><li><span>3</span><div><strong>Upload through SFTP</strong><p>The task folder lands under the trainer’s `/incoming` directory.</p></div></li><li><span>4</span><div><strong>Run from SSH menu</strong><p>The system validates `task.toml`, creates the child, streams events, collects results, then destroys the child.</p></div></li></ol>
        </section>
        <section className="surface">
          <div className="surface-head"><div><h2>Lifecycle policy</h2><p>Controls currently enforced by the control plane.</p></div><Server size={18} /></div>
          <div className="policy-list"><div><span>Parent per trainer</span><strong>1</strong></div><div><span>Concurrent child runs</span><strong>2 default</strong></div><div><span>Parent idle pause</span><strong>15 minutes</strong></div><div><span>Parent image refresh</span><strong>24 hours</strong></div><div><span>Child cleanup</span><strong>After result finalization</strong></div><div><span>Durable handoff</span><strong>Parent + artifact store</strong></div></div>
        </section>
        <section className="surface">
          <div className="surface-head"><div><h2>Current cost posture</h2><p>Local adapter estimates; cloud provider billing remains authoritative.</p></div><CircleDollarSign size={18} /></div>
          <div className="cost-block"><span><small>Recorded child runs</small><strong>${Number(data?.costs?.run_cost || 0).toFixed(4)}</strong></span><span><small>Running parents</small><strong>{data?.costs?.active_parents ?? 0}</strong></span><span><small>Parent hourly estimate</small><strong>${Number(data?.costs?.active_parent_hourly_estimate || 0).toFixed(2)}/h</strong></span></div>
          <div className="runtime-note"><Status value={runtime.harbor_enabled ? 'HARBOR ENABLED' : 'HARBOR DISABLED'} /><p>Runtime mode is controlled by deployment configuration. The UI never stores or displays provider secrets.</p></div>
        </section>
      </div>
      <Notice notice={notice} onClose={clear} />
    </>
  )
}
