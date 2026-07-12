import React from 'react'
import { AlertTriangle, Check, ChevronRight, Circle, Copy, Download, X } from 'lucide-react'

export const ACTIVE_STATES = ['QUEUED', 'PROVISIONING', 'STAGING_INPUTS', 'RUNNING', 'COLLECTING_OUTPUTS', 'FINALIZING']

export function classNames(...values) {
  return values.filter(Boolean).join(' ')
}

export function shortId(value, size = 8) {
  if (!value) return '-'
  return value.length > size + 4 ? `${value.slice(0, size)}…${value.slice(-4)}` : value
}

export function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function formatDuration(value) {
  if (value === null || value === undefined) return '-'
  const minutes = Math.floor(value / 60)
  const seconds = value % 60
  return minutes ? `${minutes}m ${String(seconds).padStart(2, '0')}s` : `${seconds}s`
}

export function formatBytes(value) {
  let size = Number(value || 0)
  for (const unit of ['B', 'KB', 'MB', 'GB']) {
    if (size < 1024 || unit === 'GB') return `${unit === 'B' ? Math.round(size) : size.toFixed(1)} ${unit}`
    size /= 1024
  }
  return `${size.toFixed(1)} GB`
}

export function Status({ value, dot = true }) {
  const state = String(value || 'UNKNOWN').toUpperCase()
  const tone = state.includes('FAIL') || state.includes('ERROR') || state.includes('TIME') || state === 'DESTROYED' || state === 'DISABLED'
    ? 'danger'
    : state.includes('RUN') || state.includes('ACTIVE') || state.includes('SUCCEED') || state === 'READY'
      ? 'success'
      : state.includes('QUEUE') || state.includes('PAUSE') || state.includes('REFRESH') || state.includes('COLLECT') || state.includes('FINAL') || state.includes('PROVISION')
        ? 'warning'
        : 'neutral'
  return <span className={`status status-${tone}`}>{dot && <Circle size={7} fill="currentColor" />}{state.replaceAll('_', ' ')}</span>
}

export function Id({ value, copy = false }) {
  return (
    <span className="id-value" title={value || ''}>
      {shortId(value)}
      {copy && value && <button className="inline-icon" title="Copy ID" onClick={(event) => { event.stopPropagation(); navigator.clipboard.writeText(value) }}><Copy size={12} /></button>}
    </span>
  )
}

export function PageHeader({ title, description, actions }) {
  return <div className="page-header"><div><h1>{title}</h1><p>{description}</p></div><div className="header-actions">{actions}</div></div>
}

export function Toolbar({ children, count }) {
  return <div className="toolbar">{children}<span className="toolbar-count">{count ?? 0} records</span></div>
}

export function Table({ columns, children, empty = 'No records match these filters.' }) {
  const hasRows = React.Children.count(children) > 0
  return (
    <div className="table-frame">
      <table className="data-table">
        <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>{hasRows ? children : <tr><td colSpan={columns.length} className="empty-cell">{empty}</td></tr>}</tbody>
      </table>
    </div>
  )
}

export function Inspector({ title, subtitle, status, onClose, children, actions }) {
  return (
    <aside className="inspector">
      <div className="inspector-head">
        <div><span className="inspector-label">Selected record</span><h2>{title}</h2><p>{subtitle}</p></div>
        <button className="icon-button" onClick={onClose} title="Close inspector"><X size={17} /></button>
      </div>
      <div className="inspector-state">{status}</div>
      <div className="inspector-body">{children}</div>
      {actions && <div className="inspector-actions">{actions}</div>}
    </aside>
  )
}

export function DetailList({ items }) {
  return <dl className="detail-list">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? '-'}</dd></div>)}</dl>
}

export function Modal({ title, description, onClose, children, actions, danger = false }) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <section className="modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal-head">
          <span className={danger ? 'modal-icon danger' : 'modal-icon'}>{danger ? <AlertTriangle size={18} /> : <Check size={18} />}</span>
          <div><h2>{title}</h2>{description && <p>{description}</p>}</div>
          <button className="icon-button" onClick={onClose} title="Close"><X size={17} /></button>
        </div>
        <div className="modal-body">{children}</div>
        <div className="modal-actions">{actions}</div>
      </section>
    </div>
  )
}

export function Notice({ notice, onClose }) {
  if (!notice) return null
  return <div className={`toast toast-${notice.tone}`}><span>{notice.message}</span><button onClick={onClose}><X size={14} /></button></div>
}

export function ArtifactButton({ artifact, onDownload }) {
  return (
    <button className="artifact" onClick={onDownload}>
      <span><strong>{artifact.path}</strong><small>{formatBytes(artifact.size_bytes)} · {artifact.sha256?.slice(0, 12)}</small></span>
      <Download size={15} />
    </button>
  )
}

export function Lineage({ run }) {
  return (
    <div className="lineage compact">
      <span><small>Trainer</small><strong>@{run.username}</strong></span><ChevronRight size={14} />
      <span><small>Parent</small><strong>{shortId(run.parent_sandbox_id)}</strong></span><ChevronRight size={14} />
      <span><small>Child</small><strong>{shortId(run.container_id) || '-'}</strong></span><ChevronRight size={14} />
      <span><small>Result</small><strong>{run.artifact_count ? 'Ready' : 'Pending'}</strong></span>
    </div>
  )
}
