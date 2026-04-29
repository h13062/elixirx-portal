import { useEffect, useState, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Shield,
  Clock,
  AlertTriangle,
  CheckCircle,
  Download,
  Plus,
  ChevronDown,
  Trash2,
} from 'lucide-react'
import { useAuth } from '../lib/auth'
import {
  apiGet,
  apiGetOptional,
  apiPut,
  apiPostAuth,
  apiGetBlob,
  apiDelete,
} from '../lib/api'
import ConfirmModal from '../components/ConfirmModal'
import './MachineDetail.css'

// ─── Types ────────────────────────────────────────────────────────────────

interface MachineInfo {
  id: string
  serial_number: string
  product_id: string
  product_name: string | null
  product_sku: string | null
  machine_type: string | null
  batch_number: string
  manufacture_date: string
  status: string
  reserved_by: string | null
  reservation_expires_at: string | null
  registered_by: string
  created_at: string
  updated_at: string
}

interface ProductInfo {
  id: string
  name: string
  category: string
  default_price: number
  sku: string | null
  description: string | null
}

interface StatusLogEntry {
  id: string
  from_status: string | null
  to_status: string
  changed_by: string | null
  changed_by_name: string | null
  reason: string | null
  created_at: string
}

interface FullDetail {
  machine: MachineInfo
  product: ProductInfo | null
  status_history: StatusLogEntry[]
}

interface Warranty {
  id: string
  machine_id: string
  serial_number: string | null
  customer_name: string | null
  customer_contact: string | null
  duration_months: number
  start_date: string
  end_date: string
  status: string
  extended: boolean
  extension_reason: string | null
  original_end_date: string | null
  set_by_name: string | null
  days_remaining: number | null
}

interface Reservation {
  id: string
  machine_id: string
  serial_number: string | null
  reserved_by: string | null
  reserved_by_name: string | null
  reserved_for: string | null
  status: string
  expires_at: string | null
  created_at: string
}

interface Issue {
  id: string
  machine_id: string
  serial_number: string | null
  reported_by: string | null
  reported_by_name: string | null
  title: string
  description: string | null
  priority: string
  status: string
  resolved_by: string | null
  resolved_by_name: string | null
  resolution_notes: string | null
  created_at: string
  updated_at: string
}

// ─── Date helpers ─────────────────────────────────────────────────────────

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return value
  }
}

function formatRelative(value: string | null | undefined): string {
  if (!value) return ''
  const then = new Date(value).getTime()
  const now = Date.now()
  const diff = Math.max(0, Math.floor((now - then) / 1000))
  if (diff < 60) return 'just now'
  if (diff < 3600) {
    const m = Math.floor(diff / 60)
    return `${m} minute${m === 1 ? '' : 's'} ago`
  }
  if (diff < 86400) {
    const h = Math.floor(diff / 3600)
    return `${h} hour${h === 1 ? '' : 's'} ago`
  }
  if (diff < 86400 * 7) {
    const d = Math.floor(diff / 86400)
    return `${d} day${d === 1 ? '' : 's'} ago`
  }
  return formatDate(value)
}

// Valid forward transitions — mirrors VALID_TRANSITIONS in backend
// machine_lifecycle_service.py. When force=true is set, ALL_STATUSES is shown.
const VALID_TRANSITIONS: Record<string, string[]> = {
  available: ['reserved'],
  reserved: ['available', 'ordered'],
  ordered: ['sold', 'available'],
  sold: ['delivered', 'available'],
  delivered: ['returned'],
  returned: ['available'],
}

const ALL_STATUSES = [
  'available', 'reserved', 'ordered', 'sold', 'delivered', 'returned',
] as const

/** Add `months` to a date, clamping the day to the last day of the target month. */
function addMonths(date: Date, months: number): Date {
  const result = new Date(date.getFullYear(), date.getMonth() + months, 1)
  const lastDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate()
  result.setDate(Math.min(date.getDate(), lastDay))
  return result
}

function formatDateOnly(d: Date): string {
  return d.toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

function reservationCountdown(expiresAt: string | null): string {
  if (!expiresAt) return ''
  const target = new Date(expiresAt).getTime()
  const now = Date.now()
  const diff = target - now
  if (diff <= 0) return 'expired'
  const days = Math.floor(diff / 86400000)
  const hours = Math.floor((diff % 86400000) / 3600000)
  if (days > 0) return `${days}d ${hours}h remaining`
  return `${hours}h remaining`
}

// ─── Component ────────────────────────────────────────────────────────────

export default function MachineDetail() {
  const { identifier } = useParams<{ identifier: string }>()
  const navigate = useNavigate()
  const { access_token, user } = useAuth()
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'

  const [detail, setDetail] = useState<FullDetail | null>(null)
  const [warranty, setWarranty] = useState<Warranty | null>(null)
  const [reservation, setReservation] = useState<Reservation | null>(null)
  const [issues, setIssues] = useState<Issue[]>([])

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [toast, setToast] = useState<{ kind: 'success' | 'error' | 'info'; msg: string } | null>(null)

  // Modals
  const [showReportIssue, setShowReportIssue] = useState(false)
  const [resolveTarget, setResolveTarget] = useState<Issue | null>(null)
  const [closeTarget, setCloseTarget] = useState<Issue | null>(null)
  const [showSetWarranty, setShowSetWarranty] = useState(false)
  const [showExtendWarranty, setShowExtendWarranty] = useState(false)

  // History pagination
  const [showAllHistory, setShowAllHistory] = useState(false)

  // Tab state for the History | Issues section
  const [detailTab, setDetailTab] = useState<'history' | 'issues'>('history')

  // Actions dropdown menu (admin)
  const [showActionsMenu, setShowActionsMenu] = useState(false)

  // Delete confirmation state
  const [confirmDeleteMachine, setConfirmDeleteMachine] = useState(false)
  const [deleteIssue, setDeleteIssue] = useState<Issue | null>(null)

  // Sprint 3.7 admin actions
  const [showStatusModal, setShowStatusModal] = useState(false)
  const [showReserveModal, setShowReserveModal] = useState(false)
  const [denyTarget, setDenyTarget] = useState<Reservation | null>(null)
  const [downloadingCert, setDownloadingCert] = useState(false)

  // ── Data fetch ──────────────────────────────────────────────────────────

  const fetchAll = useCallback(async () => {
    if (!identifier || !access_token) return
    setLoading(true)
    setError(null)
    setNotFound(false)
    try {
      // Full-detail + issues — these SHOULD return 200; treat anything else
      // as a real error. Issues failing in particular shouldn't kill the page.
      const [d, issuesRes] = await Promise.all([
        apiGet<FullDetail>(`/api/machines/${identifier}/full-detail`, access_token),
        apiGet<Issue[]>(`/api/issues/machine/${identifier}`, access_token).catch((e) => {
          console.error('Issues fetch failed:', e)
          return [] as Issue[]
        }),
      ])
      setDetail(d)
      setIssues(issuesRes || [])

      // Warranty: 404 = "no warranty yet" (expected). 500/network = real error
      // — log it but don't block the page; the card will show "No warranty set".
      try {
        const w = await apiGetOptional<Warranty>(
          `/api/warranty/machine/${identifier}`,
          access_token,
        )
        setWarranty(w)
      } catch (e) {
        console.error('Warranty fetch error:', e)
        setWarranty(null)
      }

      // Reservation: 404 = "no active reservation". Same pattern as warranty.
      try {
        const r = await apiGetOptional<Reservation>(
          `/api/reservations/machine/${identifier}`,
          access_token,
        )
        setReservation(r)
      } catch (e) {
        console.error('Reservation fetch error:', e)
        setReservation(null)
      }
    } catch (e) {
      const msg = (e as Error).message
      if (msg.toLowerCase().includes('machine not found')) {
        setNotFound(true)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [identifier, access_token])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  const showToast = (kind: 'success' | 'error' | 'info', msg: string) => {
    setToast({ kind, msg })
    window.setTimeout(() => setToast(null), 3000)
  }

  // ── Action handlers ─────────────────────────────────────────────────────

  const downloadCertificate = async () => {
    if (!identifier || !access_token) return
    setDownloadingCert(true)
    try {
      const blob = await apiGetBlob(`/api/warranty/certificate/${identifier}`, access_token)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const serial = detail?.machine.serial_number || identifier
      a.download = `ElixirX_Warranty_${serial}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      showToast('error', (e as Error).message || 'Failed to download certificate')
    } finally {
      setDownloadingCert(false)
    }
  }

  const restockMachine = async () => {
    if (!identifier) return
    try {
      await apiPut(
        `/api/machines/${encodeURIComponent(identifier)}/status`,
        { new_status: 'available', reason: 'Restocked' },
        access_token!,
      )
      showToast('success', 'Machine restocked')
      fetchAll()
    } catch (e) {
      showToast('error', (e as Error).message)
    }
  }

  const approveReservation = async () => {
    if (!reservation) return
    try {
      await apiPut(
        `/api/reservations/${reservation.id}/approve`,
        {},
        access_token!,
      )
      showToast('success', 'Reservation approved')
      fetchAll()
    } catch (e) {
      showToast('error', (e as Error).message)
    }
  }

  const cancelReservation = async () => {
    if (!reservation) return
    if (!window.confirm('Cancel this reservation?')) return
    try {
      await apiPut(`/api/reservations/${reservation.id}/cancel`, {}, access_token!)
      showToast('success', 'Reservation cancelled')
      fetchAll()
    } catch (e) {
      showToast('error', (e as Error).message)
    }
  }

  const performDeleteMachine = async () => {
    if (!identifier) return
    await apiDelete(
      `/api/machines/${encodeURIComponent(identifier)}`,
      access_token!,
    )
    // Bounce back to inventory; toast is shown there via location state
    navigate('/inventory')
  }

  const performDeleteIssue = async () => {
    if (!deleteIssue) return
    await apiDelete(`/api/issues/${deleteIssue.id}`, access_token!)
    setDeleteIssue(null)
    showToast('success', 'Issue deleted')
    fetchAll()
  }

  const markIssueInProgress = async (issue: Issue) => {
    try {
      await apiPut(
        `/api/issues/${issue.id}/status`,
        { status: 'in_progress' },
        access_token!,
      )
      showToast('success', 'Issue marked in progress')
      fetchAll()
    } catch (e) {
      showToast('error', (e as Error).message)
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────

  if (notFound) {
    return (
      <div className="md-not-found">
        <h2>Machine not found</h2>
        <p>No machine matches "{identifier}".</p>
        <button className="md-btn md-btn-primary" onClick={() => navigate('/inventory')}>
          <ArrowLeft size={16} /> Back to Inventory
        </button>
      </div>
    )
  }

  if (loading || !detail) {
    return (
      <div className="md-page">
        <div className="md-skeleton md-skel-header" />
        <div className="md-cards-row">
          <div className="md-skeleton md-skel-card" />
          <div className="md-skeleton md-skel-card" />
          <div className="md-skeleton md-skel-card" />
        </div>
        <div className="md-skeleton md-skel-block" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="md-page">
        <div className="md-error-banner">
          <AlertTriangle size={16} /> {error}
          <button className="md-btn md-btn-ghost" onClick={fetchAll}>
            Retry
          </button>
        </div>
      </div>
    )
  }

  const { machine, product, status_history } = detail
  const machineType = machine.machine_type
  const visibleHistory = showAllHistory ? status_history : status_history.slice(0, 10)
  const canCancelReservation =
    isAdmin || (reservation && reservation.reserved_by === user?.id)

  return (
    <div className="md-page">
      {/* ── BACK LINK ──────────────────────────────────────────────────── */}
      <button className="md-back-link" onClick={() => navigate('/inventory')}>
        <ArrowLeft size={14} /> Back to Inventory
      </button>

      {/* ── HEADER BAR ─────────────────────────────────────────────────── */}
      <div className="md-header">
        <h1 className="md-serial">{machine.serial_number}</h1>
        {(machineType === 'RX' || machineType === 'RO') && (
          <span className={`md-type-badge ${machineType.toLowerCase()}`}>{machineType}</span>
        )}
        <span className={`status-badge status-${machine.status}`}>
          <span className="status-dot" />
          {machine.status.charAt(0).toUpperCase() + machine.status.slice(1)}
        </span>

        <div className="md-header-spacer" />

        <div className="md-actions-wrap">
          <button
            className="md-btn md-btn-primary"
            onClick={() => setShowActionsMenu(v => !v)}
          >
            Actions <ChevronDown size={14} />
          </button>
          {showActionsMenu && (
            <>
              <div
                className="md-actions-backdrop"
                onClick={() => setShowActionsMenu(false)}
              />
              <div className="md-actions-menu">
                {/* Status-specific admin actions */}
                {isAdmin && machine.status === 'available' && (
                  <button
                    className="md-actions-menu-item"
                    onClick={() => { setShowActionsMenu(false); setShowReserveModal(true) }}
                  >
                    <Clock size={14} /> Reserve Machine
                  </button>
                )}

                {isAdmin && machine.status === 'reserved' && reservation && (
                  <button
                    className="md-actions-menu-item"
                    onClick={() => { setShowActionsMenu(false); cancelReservation() }}
                  >
                    Cancel Reservation
                  </button>
                )}

                {isAdmin && machine.status === 'delivered' && !warranty && (
                  <button
                    className="md-actions-menu-item"
                    onClick={() => { setShowActionsMenu(false); setShowSetWarranty(true) }}
                  >
                    <Shield size={14} /> Set Warranty
                  </button>
                )}

                {isAdmin && machine.status === 'delivered' && warranty && (
                  <>
                    <button
                      className="md-actions-menu-item"
                      onClick={() => { setShowActionsMenu(false); setShowExtendWarranty(true) }}
                    >
                      <Shield size={14} /> Extend Warranty
                    </button>
                    <button
                      className="md-actions-menu-item"
                      onClick={() => { setShowActionsMenu(false); downloadCertificate() }}
                      disabled={downloadingCert}
                    >
                      <Download size={14} /> {downloadingCert ? 'Generating…' : 'Download Certificate'}
                    </button>
                  </>
                )}

                {isAdmin && machine.status === 'returned' && (
                  <button
                    className="md-actions-menu-item"
                    onClick={() => { setShowActionsMenu(false); restockMachine() }}
                  >
                    Restock (→ Available)
                  </button>
                )}

                {isAdmin && (
                  <button
                    className="md-actions-menu-item"
                    onClick={() => { setShowActionsMenu(false); setShowStatusModal(true) }}
                  >
                    Change Status ›
                  </button>
                )}

                {isAdmin && <div className="md-menu-divider" />}

                {/* Always available — including reps */}
                <button
                  className="md-actions-menu-item"
                  onClick={() => { setShowActionsMenu(false); setShowReportIssue(true) }}
                >
                  <AlertTriangle size={14} /> Report Issue
                </button>

                {isAdmin && (
                  <>
                    <div className="md-menu-divider" />
                    <button
                      className="md-actions-menu-item md-actions-menu-item-danger"
                      onClick={() => { setShowActionsMenu(false); setConfirmDeleteMachine(true) }}
                    >
                      <Trash2 size={14} /> Delete Machine
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── INFO CARDS ─────────────────────────────────────────────────── */}
      <div className="md-cards-row">
        {/* Card 1 — Machine */}
        <div className="md-card">
          <div className="md-card-label">MACHINE DETAILS</div>
          <KV label="Serial" mono value={machine.serial_number} />
          <KV label="Type" value={product?.name || machine.product_name || '—'} />
          <KV label="Batch" mono value={machine.batch_number} />
          <KV label="Manufactured" value={formatDate(machine.manufacture_date)} />
          <KV label="Registered" value={formatDate(machine.created_at)} />
          {product && (
            <KV label="Default Price" value={`$${product.default_price.toFixed(2)}`} />
          )}
        </div>

        {/* Card 2 — Warranty */}
        <div className="md-card">
          <div className="md-card-label">
            <Shield size={12} /> WARRANTY
          </div>
          {!warranty ? (
            <div className="md-empty-state">
              <span>No warranty set</span>
              {isAdmin && machine.status === 'delivered' && (
                <button
                  className="md-btn md-btn-primary md-btn-sm"
                  onClick={() => setShowSetWarranty(true)}
                >
                  Set Warranty
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="md-warranty-status-row">
                <span className={`md-status-pill md-status-${warranty.status}`}>
                  {warranty.status.replace('_', ' ')}
                </span>
                <span
                  className={`md-days-remaining ${
                    (warranty.days_remaining ?? 0) < 0
                      ? 'expired'
                      : (warranty.days_remaining ?? 0) <= 30
                      ? 'soon'
                      : 'ok'
                  }`}
                >
                  {(warranty.days_remaining ?? 0) < 0
                    ? `${Math.abs(warranty.days_remaining ?? 0)}d expired`
                    : `${warranty.days_remaining ?? 0}d remaining`}
                </span>
              </div>
              <KV label="Duration" value={`${warranty.duration_months} months`} />
              <KV label="Start" value={formatDate(warranty.start_date)} />
              <KV label="End" value={formatDate(warranty.end_date)} />
              <KV label="Customer" value={warranty.customer_name || '—'} />
              <KV label="Contact" value={warranty.customer_contact || '—'} />
              {warranty.extended && (
                <>
                  <KV label="Extended" value="Yes" />
                  {warranty.original_end_date && (
                    <KV
                      label="Original End"
                      value={formatDate(warranty.original_end_date)}
                    />
                  )}
                  {warranty.extension_reason && (
                    <KV label="Reason" value={warranty.extension_reason} />
                  )}
                </>
              )}
              <div className="md-card-actions">
                {isAdmin && (
                  <button
                    className="md-btn md-btn-ghost md-btn-sm"
                    onClick={() => setShowExtendWarranty(true)}
                  >
                    Extend
                  </button>
                )}
                <button className="md-btn md-btn-primary md-btn-sm" onClick={downloadCertificate}>
                  <Download size={12} /> Certificate
                </button>
              </div>
            </>
          )}
        </div>

        {/* Card 3 — Reservation */}
        <div className="md-card">
          <div className="md-card-label">
            <Clock size={12} /> RESERVATION
          </div>
          {!reservation ? (
            <div className="md-empty-state">
              <span>No active reservation</span>
              <button
                className="md-btn md-btn-primary md-btn-sm"
                disabled
                title="Coming in Task 3.9"
              >
                Reserve
              </button>
            </div>
          ) : (
            <>
              <span className={`md-status-pill md-res-${reservation.status}`}>
                {reservation.status}
              </span>
              <KV label="For" value={reservation.reserved_for || '—'} />
              <KV label="By" value={reservation.reserved_by_name || '—'} />
              {reservation.status === 'approved' && reservation.expires_at && (
                <>
                  <KV label="Expires" value={formatDate(reservation.expires_at)} />
                  <div className="md-countdown">{reservationCountdown(reservation.expires_at)}</div>
                </>
              )}
              {reservation.status === 'pending' && !isAdmin && (
                <div className="md-pending-note">Awaiting admin approval</div>
              )}
              <div className="md-card-actions">
                {reservation.status === 'pending' && isAdmin && (
                  <>
                    <button
                      className="md-btn md-btn-success md-btn-sm"
                      onClick={approveReservation}
                    >
                      Approve
                    </button>
                    <button
                      className="md-btn md-btn-danger md-btn-sm"
                      onClick={() => setDenyTarget(reservation)}
                    >
                      Deny
                    </button>
                  </>
                )}
                {canCancelReservation && reservation.status !== 'pending' && (
                  <button
                    className="md-btn md-btn-danger md-btn-sm"
                    onClick={cancelReservation}
                  >
                    Cancel Reservation
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── DETAIL TABS (History | Issues) ─────────────────────────────── */}
      <div className="md-detail-tabs">
        <button
          className={`md-detail-tab${detailTab === 'history' ? ' md-detail-tab-active' : ''}`}
          onClick={() => setDetailTab('history')}
        >
          History <span className="md-count-badge">{status_history.length}</span>
        </button>
        <button
          className={`md-detail-tab${detailTab === 'issues' ? ' md-detail-tab-active' : ''}`}
          onClick={() => setDetailTab('issues')}
        >
          Issues <span className="md-count-badge">{issues.length}</span>
        </button>
      </div>

      {detailTab === 'history' && (
      <>
      {status_history.length === 0 ? (
        <div className="md-empty-block">No status changes recorded</div>
      ) : (
        <ul className="md-timeline">
          {visibleHistory.map((entry) => (
            <li key={entry.id} className="md-timeline-item">
              <span className={`md-timeline-dot dot-${entry.to_status}`} />
              <div className="md-timeline-content">
                <div className="md-timeline-line">
                  <span className={`status-badge status-${entry.to_status}`}>
                    <span className="status-dot" />
                    {entry.to_status}
                  </span>
                  {entry.from_status && (
                    <span className="md-timeline-from">from {entry.from_status}</span>
                  )}
                  <span className="md-timeline-by">by {entry.changed_by_name || '—'}</span>
                </div>
                {entry.reason && <div className="md-timeline-reason">{entry.reason}</div>}
                <div className="md-timeline-time">{formatRelative(entry.created_at)}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {status_history.length > 10 && !showAllHistory && (
        <button
          className="md-btn md-btn-ghost md-btn-sm"
          onClick={() => setShowAllHistory(true)}
        >
          Show all {status_history.length} entries
        </button>
      )}
      </>
      )}

      {/* ── ISSUES TAB ─────────────────────────────────────────────────── */}
      {detailTab === 'issues' && (
      <>
      <div className="md-section-header">
        <div className="md-section-title">&nbsp;</div>
        <button
          className="md-btn md-btn-primary md-btn-sm"
          onClick={() => setShowReportIssue(true)}
        >
          <Plus size={14} /> Report Issue
        </button>
      </div>

      {issues.length === 0 ? (
        <div className="md-empty-block">
          <CheckCircle size={16} /> No issues reported
        </div>
      ) : (
        <div className="md-issues-list">
          {issues.map((issue) => (
            <div
              key={issue.id}
              className={`md-issue-card priority-${issue.priority}`}
            >
              <div className="md-issue-head">
                <div className="md-issue-title">{issue.title}</div>
                <span className={`md-issue-status md-issue-status-${issue.status}`}>
                  {issue.status.replace('_', ' ')}
                </span>
              </div>
              {issue.description && (
                <div className="md-issue-desc">
                  {issue.description.length > 100
                    ? issue.description.slice(0, 100) + '…'
                    : issue.description}
                </div>
              )}
              <div className="md-issue-meta">
                <span>{issue.reported_by_name || '—'}</span>
                <span>·</span>
                <span>{formatRelative(issue.created_at)}</span>
                <span>·</span>
                <span className={`md-priority-tag prio-${issue.priority}`}>
                  {issue.priority}
                </span>
              </div>
              {issue.status === 'resolved' && issue.resolution_notes && (
                <div className="md-resolution-block">
                  <strong>Resolved</strong>
                  {issue.resolved_by_name ? ` by ${issue.resolved_by_name}` : ''}: {issue.resolution_notes}
                </div>
              )}
              {isAdmin && (
                <div className="md-issue-actions">
                  {issue.status === 'open' && (
                    <button
                      className="md-btn md-btn-ghost md-btn-xs"
                      onClick={() => markIssueInProgress(issue)}
                    >
                      In Progress
                    </button>
                  )}
                  {(issue.status === 'open' || issue.status === 'in_progress') && (
                    <>
                      <button
                        className="md-btn md-btn-success md-btn-xs"
                        onClick={() => setResolveTarget(issue)}
                      >
                        Resolve
                      </button>
                      <button
                        className="md-btn md-btn-ghost md-btn-xs"
                        onClick={() => setCloseTarget(issue)}
                      >
                        Close
                      </button>
                    </>
                  )}
                  <button
                    className="md-btn md-btn-danger md-btn-xs md-issue-delete-btn"
                    title="Delete issue"
                    onClick={() => setDeleteIssue(issue)}
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      </>
      )}

      {/* ── MODALS ─────────────────────────────────────────────────────── */}
      {showReportIssue && (
        <ReportIssueModal
          serial={machine.serial_number}
          identifier={identifier!}
          token={access_token!}
          onClose={() => setShowReportIssue(false)}
          onCreated={() => {
            setShowReportIssue(false)
            showToast('success', 'Issue reported')
            fetchAll()
          }}
        />
      )}
      {resolveTarget && (
        <IssueStatusNotesModal
          issue={resolveTarget}
          targetStatus="resolved"
          token={access_token!}
          onClose={() => setResolveTarget(null)}
          onDone={() => {
            setResolveTarget(null)
            showToast('success', 'Issue resolved')
            fetchAll()
          }}
        />
      )}
      {closeTarget && (
        <IssueStatusNotesModal
          issue={closeTarget}
          targetStatus="closed"
          token={access_token!}
          onClose={() => setCloseTarget(null)}
          onDone={() => {
            setCloseTarget(null)
            showToast('success', 'Issue closed')
            fetchAll()
          }}
        />
      )}
      {showSetWarranty && (
        <SetWarrantyModal
          identifier={identifier!}
          serial={machine.serial_number}
          token={access_token!}
          onClose={() => setShowSetWarranty(false)}
          onCreated={() => {
            setShowSetWarranty(false)
            showToast('success', 'Warranty created')
            fetchAll()
          }}
        />
      )}
      {showExtendWarranty && warranty && (
        <ExtendWarrantyModal
          warranty={warranty}
          token={access_token!}
          onClose={() => setShowExtendWarranty(false)}
          onDone={() => {
            setShowExtendWarranty(false)
            showToast('success', 'Warranty extended')
            fetchAll()
          }}
        />
      )}

      {showStatusModal && (
        <StatusChangeModal
          identifier={identifier!}
          currentStatus={machine.status}
          token={access_token!}
          onClose={() => setShowStatusModal(false)}
          onUpdated={(newStatus, warrantyRequired) => {
            setShowStatusModal(false)
            showToast('success', `Status updated to ${newStatus}`)
            fetchAll()
            if (warrantyRequired && !warranty) {
              showToast('info', 'Machine delivered! Set up the warranty now.')
              setShowSetWarranty(true)
            }
          }}
        />
      )}
      {showReserveModal && (
        <ReserveMachineModal
          identifier={identifier!}
          serial={machine.serial_number}
          token={access_token!}
          onClose={() => setShowReserveModal(false)}
          onCreated={() => {
            setShowReserveModal(false)
            showToast('success', 'Reservation created — awaiting approval')
            fetchAll()
          }}
        />
      )}
      {denyTarget && (
        <DenyReservationModal
          reservation={denyTarget}
          token={access_token!}
          onClose={() => setDenyTarget(null)}
          onDone={() => {
            setDenyTarget(null)
            showToast('success', 'Reservation denied')
            fetchAll()
          }}
        />
      )}

      {confirmDeleteMachine && (
        <ConfirmModal
          title="Remove Machine"
          message={
            <>
              Are you sure you want to remove machine{' '}
              <strong>{machine.serial_number}</strong>? This action cannot be undone.
            </>
          }
          warning="If this machine has an active warranty, reservation, or open issues, the server will block the delete and prompt you to remove them first."
          confirmLabel="Remove"
          confirmKind="danger"
          onConfirm={performDeleteMachine}
          onCancel={() => setConfirmDeleteMachine(false)}
        />
      )}
      {deleteIssue && (
        <ConfirmModal
          title="Delete Issue"
          message={
            <>
              Delete this issue: <strong>{deleteIssue.title}</strong>?
            </>
          }
          confirmLabel="Delete"
          confirmKind="danger"
          onConfirm={performDeleteIssue}
          onCancel={() => setDeleteIssue(null)}
        />
      )}

      {toast && (
        <div className={`md-toast md-toast-${toast.kind}`}>{toast.msg}</div>
      )}
    </div>
  )
}

// ─── KV row helper ────────────────────────────────────────────────────────

function KV({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="md-kv">
      <span className="md-kv-label">{label}</span>
      <span className={`md-kv-value${mono ? ' mono' : ''}`}>{value}</span>
    </div>
  )
}

// ─── Modals ───────────────────────────────────────────────────────────────

function ReportIssueModal({
  serial,
  identifier,
  token,
  onClose,
  onCreated,
}: {
  serial: string
  identifier: string
  token: string
  onClose: () => void
  onCreated: () => void
}) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<'low' | 'medium' | 'high' | 'urgent'>('medium')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: { preventDefault(): void }) => {
    e.preventDefault()
    if (!title.trim()) {
      setErr('Title is required')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      await apiPostAuth(
        '/api/issues',
        {
          machine_id: identifier,
          title: title.trim(),
          description: description.trim() || undefined,
          priority,
        },
        token,
      )
      onCreated()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="md-modal-overlay" onClick={onClose}>
      <form
        className="md-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="md-modal-title">Report Issue for {serial}</h3>
        <label className="md-field">
          <span>Title *</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            autoFocus
          />
        </label>
        <label className="md-field">
          <span>Description</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
          />
        </label>
        <label className="md-field">
          <span>Priority</span>
          <select
            value={priority}
            onChange={(e) =>
              setPriority(e.target.value as 'low' | 'medium' | 'high' | 'urgent')
            }
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="urgent">Urgent</option>
          </select>
        </label>
        {err && <div className="md-form-error">{err}</div>}
        <div className="md-modal-actions">
          <button
            type="button"
            className="md-btn md-btn-ghost"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="md-btn md-btn-primary"
            disabled={saving}
          >
            {saving ? 'Submitting…' : 'Submit Issue'}
          </button>
        </div>
      </form>
    </div>
  )
}

function IssueStatusNotesModal({
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

  const submit = async (e: { preventDefault(): void }) => {
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

  const verb = targetStatus === 'resolved' ? 'Resolve' : 'Close'

  return (
    <div className="md-modal-overlay" onClick={onClose}>
      <form
        className="md-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="md-modal-title">
          {verb} Issue: {issue.title}
        </h3>
        <label className="md-field">
          <span>Resolution Notes *</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
            autoFocus
          />
        </label>
        {err && <div className="md-form-error">{err}</div>}
        <div className="md-modal-actions">
          <button
            type="button"
            className="md-btn md-btn-ghost"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="md-btn md-btn-success"
            disabled={saving}
          >
            {saving ? 'Saving…' : verb}
          </button>
        </div>
      </form>
    </div>
  )
}

function SetWarrantyModal({
  identifier,
  serial,
  token,
  onClose,
  onCreated,
}: {
  identifier: string
  serial: string
  token: string
  onClose: () => void
  onCreated: () => void
}) {
  const today = new Date().toISOString().slice(0, 10)
  const [duration, setDuration] = useState(12)
  const [startDate, setStartDate] = useState(today)
  const [customerName, setCustomerName] = useState('')
  const [customerContact, setCustomerContact] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: { preventDefault(): void }) => {
    e.preventDefault()
    setSaving(true)
    setErr(null)
    try {
      await apiPostAuth(
        '/api/warranty',
        {
          machine_id: identifier,
          duration_months: duration,
          start_date: startDate,
          customer_name: customerName.trim() || undefined,
          customer_contact: customerContact.trim() || undefined,
        },
        token,
      )
      onCreated()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="md-modal-overlay" onClick={onClose}>
      <form
        className="md-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="md-modal-title">Set Warranty for {serial}</h3>
        <label className="md-field">
          <span>Duration (months)</span>
          <input
            type="number"
            min={1}
            value={duration}
            onChange={(e) => setDuration(parseInt(e.target.value || '12', 10))}
          />
        </label>
        <label className="md-field">
          <span>Start Date</span>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </label>
        <label className="md-field">
          <span>Customer Name</span>
          <input
            value={customerName}
            onChange={(e) => setCustomerName(e.target.value)}
          />
        </label>
        <label className="md-field">
          <span>Customer Contact</span>
          <input
            value={customerContact}
            onChange={(e) => setCustomerContact(e.target.value)}
          />
        </label>
        <p className="md-modal-sub">
          End date:{' '}
          {(() => {
            const start = startDate ? new Date(startDate + 'T00:00:00') : new Date()
            return formatDateOnly(addMonths(start, duration || 0))
          })()}
        </p>
        {err && <div className="md-form-error">{err}</div>}
        <div className="md-modal-actions">
          <button
            type="button"
            className="md-btn md-btn-ghost"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="md-btn md-btn-success"
            disabled={saving}
          >
            {saving ? 'Creating…' : 'Set Warranty'}
          </button>
        </div>
      </form>
    </div>
  )
}

function ExtendWarrantyModal({
  warranty,
  token,
  onClose,
  onDone,
}: {
  warranty: Warranty
  token: string
  onClose: () => void
  onDone: () => void
}) {
  const [months, setMonths] = useState(6)
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: { preventDefault(): void }) => {
    e.preventDefault()
    if (!reason.trim()) {
      setErr('Reason is required')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      await apiPut(
        `/api/warranty/${warranty.id}/extend`,
        { additional_months: months, reason: reason.trim() },
        token,
      )
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="md-modal-overlay" onClick={onClose}>
      <form
        className="md-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="md-modal-title">Extend Warranty — {warranty.serial_number || ''}</h3>
        <p className="md-modal-sub">
          Currently ends {formatDate(warranty.end_date)}
          {' · '}
          duration {warranty.duration_months}mo
          {warranty.days_remaining != null && ` · ${warranty.days_remaining} days remaining`}
        </p>
        <label className="md-field">
          <span>Additional Months</span>
          <input
            type="number"
            min={1}
            max={60}
            value={months}
            onChange={(e) => setMonths(parseInt(e.target.value || '6', 10))}
          />
        </label>
        <label className="md-field">
          <span>Reason *</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Why is this warranty being extended?"
          />
        </label>
        <p className="md-modal-sub">
          New end date:{' '}
          {formatDateOnly(addMonths(new Date(warranty.end_date + 'T00:00:00'), months || 0))}
        </p>
        {err && <div className="md-form-error">{err}</div>}
        <div className="md-modal-actions">
          <button
            type="button"
            className="md-btn md-btn-ghost"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="md-btn md-btn-primary"
            disabled={saving}
          >
            {saving ? 'Extending…' : 'Extend Warranty'}
          </button>
        </div>
      </form>
    </div>
  )
}

// ─── Sprint 3.7 admin action modals ───────────────────────────────────────

function StatusChangeModal({
  identifier,
  currentStatus,
  token,
  onClose,
  onUpdated,
}: {
  identifier: string
  currentStatus: string
  token: string
  onClose: () => void
  onUpdated: (newStatus: string, warrantyRequired: boolean) => void
}) {
  const [force, setForce] = useState(false)
  const allowed = force
    ? ALL_STATUSES.filter(s => s !== currentStatus)
    : VALID_TRANSITIONS[currentStatus] || []
  const [newStatus, setNewStatus] = useState<string>(allowed[0] || '')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  // When force is toggled, reset newStatus to a valid option in the new list
  const handleForceToggle = (checked: boolean) => {
    setForce(checked)
    const nextAllowed = checked
      ? ALL_STATUSES.filter(s => s !== currentStatus)
      : VALID_TRANSITIONS[currentStatus] || []
    if (!nextAllowed.includes(newStatus)) {
      setNewStatus(nextAllowed[0] || '')
    }
  }

  const submit = async (e: { preventDefault(): void }) => {
    e.preventDefault()
    if (!newStatus) {
      setErr('No valid transitions from this status')
      return
    }
    if (!reason.trim()) {
      setErr('Reason is required')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      const resp = await apiPut<{
        machine: { status: string }
        warranty_setup_required: boolean
      }>(
        `/api/machines/${encodeURIComponent(identifier)}/status`,
        { new_status: newStatus, reason: reason.trim(), force },
        token,
      )
      onUpdated(resp.machine.status, !!resp.warranty_setup_required)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="md-modal-overlay" onClick={onClose}>
      <form
        className="md-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="md-modal-title">Change Machine Status</h3>
        <div className="md-modal-sub">
          Current:{' '}
          <span className={`status-badge status-${currentStatus}`}>
            <span className="status-dot" />
            {currentStatus}
          </span>
        </div>
        <label className="md-field">
          <span>New Status</span>
          <select
            value={newStatus}
            onChange={(e) => setNewStatus(e.target.value)}
          >
            {allowed.length === 0 && <option value="">— no valid transitions —</option>}
            {allowed.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="md-field">
          <span>Reason *</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Why is the status changing?"
          />
        </label>
        <label className="md-checkbox-row">
          <input
            type="checkbox"
            checked={force}
            onChange={(e) => handleForceToggle(e.target.checked)}
          />
          <span>Force override (bypass transition rules)</span>
        </label>
        {force && (
          <div className="md-warning-text">
            Force override will be logged in the audit trail (prefixed FORCED:).
          </div>
        )}
        {err && <div className="md-form-error">{err}</div>}
        <div className="md-modal-actions">
          <button
            type="button"
            className="md-btn md-btn-ghost"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="md-btn md-btn-primary"
            disabled={saving || !newStatus}
          >
            {saving ? 'Updating…' : 'Update Status'}
          </button>
        </div>
      </form>
    </div>
  )
}

function ReserveMachineModal({
  identifier,
  serial,
  token,
  onClose,
  onCreated,
}: {
  identifier: string
  serial: string
  token: string
  onClose: () => void
  onCreated: () => void
}) {
  const [reservedFor, setReservedFor] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: { preventDefault(): void }) => {
    e.preventDefault()
    if (!reservedFor.trim()) {
      setErr('Customer / lead name is required')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      await apiPostAuth(
        '/api/reservations',
        { machine_id: identifier, reserved_for: reservedFor.trim() },
        token,
      )
      onCreated()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="md-modal-overlay" onClick={onClose}>
      <form
        className="md-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="md-modal-title">Reserve Machine — {serial}</h3>
        <p className="md-modal-sub">
          The machine will go to <code>pending</code> until an admin approves.
        </p>
        <label className="md-field">
          <span>Customer / Lead *</span>
          <input
            value={reservedFor}
            onChange={(e) => setReservedFor(e.target.value)}
            autoFocus
            placeholder="e.g. Heights Nail Spa"
          />
        </label>
        {err && <div className="md-form-error">{err}</div>}
        <div className="md-modal-actions">
          <button
            type="button"
            className="md-btn md-btn-ghost"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="md-btn md-btn-primary"
            disabled={saving}
          >
            {saving ? 'Reserving…' : 'Submit Reservation'}
          </button>
        </div>
      </form>
    </div>
  )
}

function DenyReservationModal({
  reservation,
  token,
  onClose,
  onDone,
}: {
  reservation: Reservation
  token: string
  onClose: () => void
  onDone: () => void
}) {
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: { preventDefault(): void }) => {
    e.preventDefault()
    if (!reason.trim()) {
      setErr('Reason is required')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      await apiPut(
        `/api/reservations/${reservation.id}/deny`,
        { reason: reason.trim() },
        token,
      )
      onDone()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="md-modal-overlay" onClick={onClose}>
      <form
        className="md-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="md-modal-title">Deny Reservation</h3>
        <p className="md-modal-sub">
          Reservation for <strong>{reservation.reserved_for || '—'}</strong>
        </p>
        <label className="md-field">
          <span>Reason *</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            autoFocus
            placeholder="Why is this reservation being denied?"
          />
        </label>
        {err && <div className="md-form-error">{err}</div>}
        <div className="md-modal-actions">
          <button
            type="button"
            className="md-btn md-btn-ghost"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="md-btn md-btn-danger"
            disabled={saving}
          >
            {saving ? 'Denying…' : 'Deny Reservation'}
          </button>
        </div>
      </form>
    </div>
  )
}
