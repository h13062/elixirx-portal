import { useEffect, useState, useCallback, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { useAuth } from '../lib/auth'
import { apiGet, apiPut } from '../lib/api'
import './Issues.css'

// ─── Types (mirror IssueResponse from backend) ────────────────────────────

type IssueStatus = 'open' | 'in_progress' | 'resolved' | 'closed'
type IssuePriority = 'urgent' | 'high' | 'medium' | 'low'

interface Issue {
  id: string
  machine_id: string
  serial_number: string | null
  product_name: string | null
  reported_by: string | null
  reported_by_name: string | null
  title: string
  description: string | null
  priority: IssuePriority
  status: IssueStatus
  resolved_by: string | null
  resolved_by_name: string | null
  resolution_notes: string | null
  created_at: string
  updated_at: string
}

interface IssueSummaryByPriority {
  urgent: number
  high: number
  medium: number
  low: number
}

interface IssueSummary {
  open: number
  in_progress: number
  resolved: number
  closed: number
  total: number
  by_priority: IssueSummaryByPriority
}

type StatusFilter = 'all' | IssueStatus
type PriorityFilter = 'all' | IssuePriority

type SortKey = 'priority' | 'title' | 'serial_number' | 'status' | 'created_at'
type SortDir = 'asc' | 'desc'

// ─── Helpers ──────────────────────────────────────────────────────────────

const PRIORITY_RANK: Record<string, number> = {
  urgent: 0, high: 1, medium: 2, low: 3,
}
const STATUS_RANK: Record<string, number> = {
  open: 0, in_progress: 1, resolved: 2, closed: 3,
}

function formatRelative(value: string): string {
  const then = new Date(value).getTime()
  const diff = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`
  return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

function parseStatus(raw: string | null): StatusFilter {
  if (raw === 'open' || raw === 'in_progress' || raw === 'resolved' || raw === 'closed') {
    return raw
  }
  return 'all'
}

function parsePriority(raw: string | null): PriorityFilter {
  if (raw === 'urgent' || raw === 'high' || raw === 'medium' || raw === 'low') {
    return raw
  }
  return 'all'
}

// ─── Component ────────────────────────────────────────────────────────────

export default function Issues() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { user, access_token } = useAuth()

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'

  const urlStatus = searchParams.get('status')
  const urlPriority = searchParams.get('priority')

  const [issues, setIssues] = useState<Issue[]>([])
  const [summary, setSummary] = useState<IssueSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null)

  // Filters
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(() => parseStatus(urlStatus))
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>(() => parsePriority(urlPriority))

  // Re-apply on URL change (e.g. user clicks a different dashboard card)
  useEffect(() => {
    setStatusFilter(parseStatus(urlStatus))
  }, [urlStatus])
  useEffect(() => {
    setPriorityFilter(parsePriority(urlPriority))
  }, [urlPriority])

  // Sort
  const [sortKey, setSortKey] = useState<SortKey>('priority')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  // Row expansion
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Action modals
  const [resolveTarget, setResolveTarget] = useState<Issue | null>(null)
  const [closeTarget, setCloseTarget] = useState<Issue | null>(null)
  const [startBusyId, setStartBusyId] = useState<string | null>(null)

  // ─── Toast auto-dismiss ─────────────────────────────────────────────────
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])

  // ─── Fetch ──────────────────────────────────────────────────────────────

  const fetchAll = useCallback(async () => {
    if (!access_token) return
    setError(null)
    try {
      const [list, sum] = await Promise.all([
        apiGet<Issue[]>('/api/issues', access_token),
        apiGet<IssueSummary>('/api/issues/summary', access_token),
      ])
      setIssues(list)
      setSummary(sum)
    } catch (e) {
      setError((e as Error).message || 'Failed to load issues')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [access_token])

  useEffect(() => {
    setRefreshing(true)
    fetchAll()
  }, [fetchAll])

  async function refresh() {
    setRefreshing(true)
    await fetchAll()
  }

  // ─── Actions ────────────────────────────────────────────────────────────

  async function handleStart(issue: Issue) {
    setStartBusyId(issue.id)
    try {
      await apiPut(
        `/api/issues/${issue.id}/status`,
        { status: 'in_progress' },
        access_token!,
      )
      setToast({ kind: 'ok', msg: 'Issue started' })
      await refresh()
    } catch (e) {
      setToast({ kind: 'err', msg: (e as Error).message || 'Failed to start' })
    } finally {
      setStartBusyId(null)
    }
  }

  // ─── Derived ────────────────────────────────────────────────────────────

  const counts = useMemo(() => {
    if (!summary) return { all: 0, open: 0, in_progress: 0, resolved: 0, closed: 0 }
    return {
      all: summary.total,
      open: summary.open,
      in_progress: summary.in_progress,
      resolved: summary.resolved,
      closed: summary.closed,
    }
  }, [summary])

  const priorityCounts = summary?.by_priority ?? { urgent: 0, high: 0, medium: 0, low: 0 }

  const filteredAndSorted = useMemo(() => {
    let out = issues
    if (statusFilter !== 'all') out = out.filter(i => i.status === statusFilter)
    if (priorityFilter !== 'all') out = out.filter(i => i.priority === priorityFilter)

    const arr = out.slice()
    const dir = sortDir === 'asc' ? 1 : -1
    arr.sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'priority':
          cmp = (PRIORITY_RANK[a.priority] ?? 99) - (PRIORITY_RANK[b.priority] ?? 99)
          // Secondary: most recent first within same priority
          if (cmp === 0) {
            cmp = new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
            // Don't flip secondary by direction — recency tiebreak stays
            return dir * (cmp === 0 ? 0 : (cmp > 0 ? 1 : -1))
          }
          break
        case 'status':
          cmp = (STATUS_RANK[a.status] ?? 99) - (STATUS_RANK[b.status] ?? 99)
          break
        case 'created_at':
          cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          break
        case 'title':
          cmp = a.title.localeCompare(b.title)
          break
        case 'serial_number':
          cmp = (a.serial_number || '').localeCompare(b.serial_number || '')
          break
      }
      return cmp * dir
    })
    return arr
  }, [issues, statusFilter, priorityFilter, sortKey, sortDir])

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      // First click on date → desc (newest first); other columns → asc
      setSortDir(key === 'created_at' ? 'desc' : 'asc')
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="iss-page">
      {toast && (
        <div className={`iss-toast iss-toast-${toast.kind}`}>{toast.msg}</div>
      )}

      {error && (
        <div className="iss-error-banner">
          <AlertTriangle size={16} />
          <span>{error}</span>
          <button className="iss-error-retry" onClick={refresh}>Retry</button>
        </div>
      )}

      {/* ── Summary cards ──────────────────────────────────────────── */}
      <div className="iss-summary-row">
        <SummaryCard
          loading={loading && !summary}
          label="OPEN"
          count={counts.open}
          color="#3B82F6"
        />
        <SummaryCard
          loading={loading && !summary}
          label="IN PROGRESS"
          count={counts.in_progress}
          color="#F59E0B"
        />
        <SummaryCard
          loading={loading && !summary}
          label="RESOLVED"
          count={counts.resolved}
          color="#10B981"
        />
        <PriorityBreakdownCard counts={priorityCounts} />
      </div>

      {/* ── Filter tabs ────────────────────────────────────────────── */}
      <div className="iss-filter-bar">
        <div className="iss-filter-group">
          {(['all', 'open', 'in_progress', 'resolved', 'closed'] as StatusFilter[]).map(s => (
            <button
              key={s}
              className={`iss-tab${statusFilter === s ? ' iss-tab-active-status' : ''}`}
              onClick={() => setStatusFilter(s)}
            >
              {s === 'all' ? 'All'
                : s === 'in_progress' ? 'In Progress'
                : s.charAt(0).toUpperCase() + s.slice(1)}
              {' '}({s === 'all' ? counts.all : counts[s as keyof typeof counts]})
            </button>
          ))}
        </div>
        <div className="iss-filter-divider" />
        <div className="iss-filter-group">
          {(['all', 'urgent', 'high', 'medium', 'low'] as PriorityFilter[]).map(p => (
            <button
              key={p}
              className={`iss-tab iss-prio-tab${priorityFilter === p ? ` iss-tab-active-${p}` : ''}`}
              onClick={() => setPriorityFilter(p)}
            >
              {p === 'all' ? 'All Priorities' : p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="iss-count-line">
        Showing <strong>{filteredAndSorted.length}</strong> of {issues.length} issue{issues.length === 1 ? '' : 's'}
        {refreshing && <span className="iss-refresh-dot"> · refreshing…</span>}
      </div>

      {/* ── Table ──────────────────────────────────────────────────── */}
      <div className="iss-table-wrap">
        <table className="iss-table">
          <thead>
            <tr>
              <SortableTh label="Priority" col="priority" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <SortableTh label="Title" col="title" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <SortableTh label="Machine S/N" col="serial_number" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <SortableTh label="Status" col="status" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <th>Reported By</th>
              <SortableTh label="Reported" col="created_at" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              {isAdmin && <th className="iss-th-right">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {loading && filteredAndSorted.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 7 : 6} className="iss-empty">
                  Loading issues…
                </td>
              </tr>
            )}
            {!loading && filteredAndSorted.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 7 : 6} className="iss-empty iss-empty-clear">
                  <CheckCircle size={32} color="#10B981" />
                  <div className="iss-empty-title">All clear!</div>
                  <div>No issues found.</div>
                </td>
              </tr>
            )}
            {filteredAndSorted.map(issue => (
              <IssueRow
                key={issue.id}
                issue={issue}
                expanded={expandedId === issue.id}
                onToggle={() =>
                  setExpandedId(prev => (prev === issue.id ? null : issue.id))
                }
                onOpenMachine={(serial) => navigate(`/machines/${serial}`)}
                isAdmin={isAdmin}
                onStart={() => handleStart(issue)}
                onResolve={() => setResolveTarget(issue)}
                onClose={() => setCloseTarget(issue)}
                startBusyId={startBusyId}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Modals ─────────────────────────────────────────────────── */}
      {resolveTarget && (
        <StatusNotesModal
          issue={resolveTarget}
          targetStatus="resolved"
          token={access_token!}
          onClose={() => setResolveTarget(null)}
          onDone={async () => {
            setResolveTarget(null)
            setToast({ kind: 'ok', msg: 'Issue resolved' })
            await refresh()
          }}
        />
      )}
      {closeTarget && (
        <StatusNotesModal
          issue={closeTarget}
          targetStatus="closed"
          token={access_token!}
          onClose={() => setCloseTarget(null)}
          onDone={async () => {
            setCloseTarget(null)
            setToast({ kind: 'ok', msg: 'Issue closed' })
            await refresh()
          }}
        />
      )}
    </div>
  )
}

// ─── SummaryCard ──────────────────────────────────────────────────────────

function SummaryCard({
  loading,
  label,
  count,
  color,
}: {
  loading: boolean
  label: string
  count: number
  color: string
}) {
  return (
    <div className="iss-card" style={{ borderLeft: `3px solid ${color}` }}>
      <div className="iss-card-label">{label}</div>
      {loading ? (
        <div className="iss-card-skel" />
      ) : (
        <div className="iss-card-count" style={{ color }}>{count}</div>
      )}
    </div>
  )
}

function PriorityBreakdownCard({ counts }: { counts: IssueSummaryByPriority }) {
  return (
    <div className="iss-card">
      <div className="iss-card-label">BY PRIORITY</div>
      <div className="iss-prio-row">
        <PrioPill color="#EF4444" label="Urgent" value={counts.urgent} />
        <PrioPill color="#F59E0B" label="High"   value={counts.high} />
        <PrioPill color="#3B82F6" label="Medium" value={counts.medium} />
        <PrioPill color="#94A3B8" label="Low"    value={counts.low} />
      </div>
    </div>
  )
}

function PrioPill({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <span className="iss-prio-pill">
      <span className="iss-prio-dot" style={{ background: color }} />
      <span className="iss-prio-label">{label}:</span>
      <span className="iss-prio-value" style={{ color }}>{value}</span>
    </span>
  )
}

// ─── SortableTh ───────────────────────────────────────────────────────────

function SortableTh({
  label,
  col,
  sortKey,
  sortDir,
  onClick,
}: {
  label: string
  col: SortKey
  sortKey: SortKey
  sortDir: SortDir
  onClick: (col: SortKey) => void
}) {
  const active = sortKey === col
  return (
    <th
      className={`iss-th-sortable${active ? ' iss-th-active' : ''}`}
      onClick={() => onClick(col)}
    >
      <span className="iss-th-inner">
        {label}
        {active && (sortDir === 'asc' ? '▲' : '▼')}
      </span>
    </th>
  )
}

// ─── IssueRow ─────────────────────────────────────────────────────────────

function IssueRow({
  issue,
  expanded,
  onToggle,
  onOpenMachine,
  isAdmin,
  onStart,
  onResolve,
  onClose,
  startBusyId,
}: {
  issue: Issue
  expanded: boolean
  onToggle: () => void
  onOpenMachine: (serial: string) => void
  isAdmin: boolean
  onStart: () => void
  onResolve: () => void
  onClose: () => void
  startBusyId: string | null
}) {
  return (
    <>
      <tr className="iss-row">
        <td>
          <span className={`iss-prio-cell iss-prio-${issue.priority}`}>
            <span className="iss-prio-dot" />
            {issue.priority.toUpperCase()}
          </span>
        </td>
        <td>
          <button className="iss-title-btn" onClick={onToggle}>
            {expanded
              ? <ChevronDown size={12} />
              : <ChevronRight size={12} />
            }
            <span className="iss-title-text">{issue.title}</span>
          </button>
        </td>
        <td>
          {issue.serial_number ? (
            <button
              className="iss-link iss-mono"
              onClick={() => onOpenMachine(issue.serial_number!)}
            >
              {issue.serial_number}
            </button>
          ) : (
            <span className="iss-mono iss-muted">{issue.machine_id.slice(0, 8)}</span>
          )}
        </td>
        <td>
          <span className={`iss-status iss-status-${issue.status}`}>
            {issue.status.replace('_', ' ')}
          </span>
        </td>
        <td className="iss-cell-by">{issue.reported_by_name || '—'}</td>
        <td className="iss-cell-rel">{formatRelative(issue.created_at)}</td>
        {isAdmin && (
          <td className="iss-cell-actions">
            {issue.status === 'open' && (
              <button
                className="iss-btn iss-btn-sm iss-btn-warn"
                onClick={onStart}
                disabled={startBusyId === issue.id}
              >
                {startBusyId === issue.id ? '…' : 'Start'}
              </button>
            )}
            {issue.status === 'in_progress' && (
              <button
                className="iss-btn iss-btn-sm iss-btn-success"
                onClick={onResolve}
              >
                Resolve
              </button>
            )}
            {(issue.status === 'open' || issue.status === 'in_progress') && (
              <button
                className="iss-btn iss-btn-sm iss-btn-ghost"
                onClick={onClose}
              >
                Close
              </button>
            )}
          </td>
        )}
      </tr>
      {expanded && (
        <tr className="iss-row-expanded">
          <td colSpan={isAdmin ? 7 : 6}>
            <div className="iss-expanded-body">
              {issue.description ? (
                <div className="iss-description">{issue.description}</div>
              ) : (
                <div className="iss-description iss-muted">
                  <em>No description provided.</em>
                </div>
              )}
              {issue.status === 'resolved' && issue.resolution_notes && (
                <div className="iss-resolution">
                  <div className="iss-resolution-head">
                    Resolution{issue.resolved_by_name && ` by ${issue.resolved_by_name}`}
                    {issue.updated_at && ` · ${formatDate(issue.updated_at)}`}
                  </div>
                  <div className="iss-resolution-body">{issue.resolution_notes}</div>
                </div>
              )}
              {issue.status === 'closed' && issue.resolution_notes && (
                <div className="iss-resolution iss-resolution-closed">
                  <div className="iss-resolution-head">
                    Closed{issue.resolved_by_name && ` by ${issue.resolved_by_name}`}
                    {issue.updated_at && ` · ${formatDate(issue.updated_at)}`}
                  </div>
                  <div className="iss-resolution-body">{issue.resolution_notes}</div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ─── StatusNotesModal (resolve / close) ───────────────────────────────────

function StatusNotesModal({
  issue,
  targetStatus,
  token,
  onClose,
  onDone,
}: {
  issue: Issue
  targetStatus: 'resolved' | 'closed'
  token: string
  onClose: () => void
  onDone: () => void
}) {
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!notes.trim()) {
      setErr('Resolution notes are required')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      await apiPut(
        `/api/issues/${issue.id}/status`,
        { status: targetStatus, resolution_notes: notes.trim() },
        token,
      )
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const verb = targetStatus === 'resolved' ? 'Resolve' : 'Close Issue'
  const title = targetStatus === 'resolved' ? 'Resolve Issue' : 'Close Issue'

  return (
    <div className="iss-modal-overlay" onClick={onClose}>
      <form
        className="iss-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="iss-modal-title">{title}</h3>
        <p className="iss-modal-sub">
          <strong>{issue.title}</strong>
          {issue.serial_number && (
            <span className="iss-mono iss-modal-machine">
              {' · '}{issue.serial_number}
            </span>
          )}
        </p>
        <label className="iss-field">
          <span>Resolution Notes *</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
            autoFocus
            placeholder={
              targetStatus === 'resolved'
                ? 'How was this issue resolved?'
                : 'Why is this issue being closed?'
            }
          />
        </label>
        {err && <div className="iss-form-error">{err}</div>}
        <div className="iss-modal-actions">
          <button
            type="button"
            className="iss-btn iss-btn-ghost"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            type="submit"
            className={`iss-btn ${targetStatus === 'resolved' ? 'iss-btn-success' : 'iss-btn-ghost-strong'}`}
            disabled={saving}
          >
            {saving ? 'Saving…' : verb}
          </button>
        </div>
      </form>
    </div>
  )
}
