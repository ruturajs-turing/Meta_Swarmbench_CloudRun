import React, { useState } from 'react'
import { ClipboardList, RefreshCcw, Search } from 'lucide-react'
import { api } from '../api.js'
import { usePolling } from '../hooks.js'
import { Id, PageHeader, Status, Table, Toolbar, formatDate } from '../ui.jsx'


export function AuditPage() {
  const [search, setSearch] = useState('')
  const { data, loading, error, refresh } = usePolling(() => api.audit(), 6000, [])
  const rows = (data?.events || []).filter((event) => !search || JSON.stringify(event).toLowerCase().includes(search.toLowerCase()))
  return (
    <>
      <PageHeader title="Operator audit" description="An append-only record of account, workspace, run, quota, and cleanup operations." actions={<button className="button" onClick={() => refresh()}><RefreshCcw size={14} />Refresh</button>} />
      {error && <div className="inline-alert danger">Audit stream failed: {error}</div>}
      <Toolbar count={rows.length}><label className="search-field"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Action, actor, target, or detail" /></label></Toolbar>
      <Table columns={['Time', 'Actor', 'Action', 'Target type', 'Target ID', 'Status', 'Detail']} empty={loading ? 'Loading audit events…' : 'No audit events match this search.'}>
        {rows.map((event) => <tr key={event.id}><td>{formatDate(event.created_at)}</td><td className="mono">@{event.actor}</td><td><strong>{event.action}</strong></td><td>{event.target_type}</td><td><Id value={event.target_id} /></td><td><Status value={event.status} /></td><td className="audit-detail" title={JSON.stringify(event.detail)}>{Object.keys(event.detail || {}).length ? JSON.stringify(event.detail) : '-'}</td></tr>)}
      </Table>
      {!rows.length && !loading && <div className="audit-empty"><ClipboardList size={22} /><span>Actions taken through the control plane will appear here.</span></div>}
    </>
  )
}
