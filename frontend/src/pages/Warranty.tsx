import { useEffect, useState, useCallback, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Shield,
  AlertTriangle,
  Download,
  Plus,
} from 'lucide-react'
import { useAuth } from '../lib/auth'
import { apiGet, apiPut, apiGetBlob } from '../lib/api'
import './Warranty.css'

// ─── Types ────────────────────────────────────────────────────────────────

type StatusFilter = 'all' | 'active' | 'expiring_soon' | 'expired'
type TypeFilter = 'all' | 'RX' | 'RO'

interface Warranty {
  id: string
  machine_id: string
  serial_number: string | null
  machine_type: string | null
  product_name: string | null
  batch_number: string | null
  customer_name: string | null
  customer_contact: string | null
  duration_months: number
  start_date: string
  end_date: string
  status: 'active' | 'expiring_soon' | 'expired'
  extended: boolean
  extension_reason: string | null
  original_end_date: string | null
  set_by_name: string | null
  days_remaining: number | null
  created_at: string
  updated_at: string
}

interface ExpiringMachine {
  warranty_id: string
  machine_id: string
  serial_number: string | null
  customer_name: string | null
  end_date: string
  days_remaining: number
}

interface Dashboard {
  active: number
  expiring_soon: number
  expired: number
  total: number
  expiring_machines: ExpiringMachine[]
}

// ─── Helpers ──────────────────────────────────────────────────────────────

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

// ─── Component ────────────────────────────────────────────────────────────

/** Coerce a `?status=...` value to a known warranty StatusFilter. */
function parseStatus(raw: string | null): StatusFilter {
  if (raw === 'active' || raw === 'expiring_soon' || raw === 'expired') return raw
  return 'all'
}

export default function Warranty() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { user, access_token } = useAuth()
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'

  const urlStatus = searchParams.get('status')

  // Route guard — sidebar already hides it for reps, but defend in depth.
  useEffect(() => {
    if (user && !isAdmin) {
      navigate('/dashboard', { replace: true })
    }
  }, [user, isAdmin, navigate])

  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [warranties, setWarranties] = useState<Warranty[]>([])
  const [expiringList, setExpiringList] = useState<ExpiringMachine[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null)

  const [statusFilter, setStatusFilter] = useState<StatusFilter>(() => parseStatus(urlStatus))
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')

  // React to `?status=...` changes after mount (e.g. user clicks a different
  // dashboard card without unmounting the page).
  useEffect(() => {
    setStatusFilter(parseStatus(urlStatus))
  }, [urlStatus])

  const [extendTarget, setExtendTarget] = useState<Warranty | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)

  // Toast auto-dismiss
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])

  // ─── Data fetching ──────────────────────────────────────────────────────

  const fetchList = useCallback(async (status: StatusFilter, type: TypeFilter) => {
    const params = new URLSearchParams()
    if (status !== 'all') params.set('status', status)
    if (type !== 'all') params.set('machine_type', type)
    const qs = params.toString()
    const path = qs ? `/api/warranty?${qs}` : '/api/warranty'
    return apiGet<Warranty[]>(path, access_token!)
  }, [access_token])

  const fetchAll = useCallback(async () => {
    setError(null)
    try {
      const [dash, list, expiring] = await Promise.all([
        apiGet<Dashboard>('/api/warranty/dashboard', access_token!),
        fetchList(statusFilter, typeFilter),
        apiGet<ExpiringMachine[]>('/api/warranty/check-expiring', access_token!),
      ])
      setDashboard(dash)
      setWarranties(list)
      setExpiringList(expiring)
    } catch (e) {
      setError((e as Error).message || 'Failed to load warranties')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [access_token, fetchList, statusFilter, typeFilter])

  // Initial load + reload when filter changes
  useEffect(() => {
    if (!access_token || !isAdmin) return
    setRefreshing(true)
    fetchAll()
  }, [access_token, isAdmin, fetchAll])

  const refreshAfterMutation = async () => {
    setRefreshing(true)
    await fetchAll()
  }

  // ─── PDF download ───────────────────────────────────────────────────────

  const handleDownload = async (w: Warranty) => {
    setDownloadingId(w.id)
    try {
      const target = w.serial_number || w.machine_id
      const blob = await apiGetBlob(`/api/warranty/certificate/${target}`, access_token!)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ElixirX_Warranty_${w.serial_number || w.machine_id}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      setToast({ kind: 'ok', msg: 'Certificate downloaded' })
    } catch (e) {
      setToast({ kind: 'err', msg: (e as Error).message || 'Download failed' })
    } finally {
      setDownloadingId(null)
    }
  }

  // ─── Derived ────────────────────────────────────────────────────────────

  const counts = useMemo(() => {
    if (!dashboard) return { all: 0, active: 0, expiring_soon: 0, expired: 0 }
    return {
      all: dashboard.total,
      active: dashboard.active,
      expiring_soon: dashboard.expiring_soon,
      expired: dashboard.expired,
    }
  }, [dashboard])

  const totalCount = dashboard?.total ?? 0
  const shownCount = warranties.length

  // ─── Render ─────────────────────────────────────────────────────────────

  if (!isAdmin) {
    // Will redirect via the effect above; render nothing in the meantime.
    return null
  }

  return (
    <div className="war-page">
      {toast && (
        <div className={`war-toast war-toast-${toast.kind}`}>{toast.msg}</div>
      )}

      {error && (
        <div className="war-error-banner">
          <AlertTriangle size={16} />
          <span>{error}</span>
          <button onClick={() => fetchAll()} className="war-error-retry">Retry</button>
        </div>
      )}

      {/* ── Summary cards ────────────────────────────────────────────── */}
      <div className="war-summary-row">
        {loading && !dashboard ? (
          <>
            <div className="war-card war-skel" />
            <div className="war-card war-skel" />
            <div className="war-card war-skel" />
            <div className="war-card war-skel" />
          </>
        ) : (
          <>
            <SummaryCard
              label="TOTAL WARRANTIES"
              count={dashboard?.total ?? 0}
              color="#F8FAFC"
              icon={<Shield size={18} color="#64748B" />}
            />
            <SummaryCard
              label="ACTIVE"
              count={dashboard?.active ?? 0}
              color="#10B981"
              accent
            />
            <SummaryCard
              label="EXPIRING SOON"
              count={dashboard?.expiring_soon ?? 0}
              color="#F59E0B"
              subtitle="within 30 days"
              accent
            />
            <SummaryCard
              label="EXPIRED"
              count={dashboard?.expired ?? 0}
              color="#EF4444"
              accent
            />
          </>
        )}
      </div>

      {/* ── Expiring-soon alert ──────────────────────────────────────── */}
      {expiringList.length > 0 && (
        <div className="war-expiring-alert">
          <div className="war-expiring-header">
            <AlertTriangle size={16} color="#F59E0B" />
            <span>Warranties expiring within 30 days</span>
          </div>
          <div className="war-expiring-list">
            {expiringList.map((m) => (
              <div className="war-expiring-row" key={m.warranty_id}>
                <button
                  className="war-link war-mono"
                  onClick={() => m.serial_number && navigate(`/machines/${m.serial_number}`)}
                  disabled={!m.serial_number}
                >
                  {m.serial_number || m.machine_id.slice(0, 8)}
                </button>
                <span className="war-expiring-customer">{m.customer_name || '—'}</span>
                <span className="war-expiring-end">{formatDate(m.end_date)}</span>
                <span className="war-expiring-days">
                  {m.days_remaining}d left
                </span>
                <button
                  className="war-btn war-btn-xs war-btn-primary"
                  onClick={() => {
                    const w = warranties.find(x => x.id === m.warranty_id)
                    if (w) setExtendTarget(w)
                  }}
                >
                  Extend
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Filter bar ───────────────────────────────────────────────── */}
      <div className="war-filter-bar">
        <div className="war-filter-tabs">
          {(['all', 'active', 'expiring_soon', 'expired'] as StatusFilter[]).map((s) => (
            <button
              key={s}
              className={`war-tab${statusFilter === s ? ' war-tab-active-status' : ''}`}
              onClick={() => setStatusFilter(s)}
            >
              {s === 'all' ? 'All'
                : s === 'active' ? 'Active'
                : s === 'expiring_soon' ? 'Expiring Soon'
                : 'Expired'} ({counts[s]})
            </button>
          ))}
        </div>

        <div className="war-filter-divider" />

        <div className="war-filter-tabs">
          {(['all', 'RX', 'RO'] as TypeFilter[]).map((t) => (
            <button
              key={t}
              className={`war-tab${typeFilter === t ? ' war-tab-active-type' : ''}`}
              onClick={() => setTypeFilter(t)}
            >
              {t === 'all' ? 'All Types' : `${t} Machine`}
            </button>
          ))}
        </div>
      </div>

      <div className="war-count-line">
        Showing <strong>{shownCount}</strong> of {totalCount} warrant{totalCount === 1 ? 'y' : 'ies'}
        {refreshing && <span className="war-refresh-dot"> · refreshing…</span>}
      </div>

      {/* ── Table ────────────────────────────────────────────────────── */}
      <div className="war-table-wrap">
        <table className="war-table">
          <thead>
            <tr>
              <th>Machine S/N</th>
              <th>Type</th>
              <th>Customer</th>
              <th>Start Date</th>
              <th>End Date</th>
              <th>Duration</th>
              <th>Days Left</th>
              <th>Status</th>
              <th className="war-th-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && warranties.length === 0 && (
              <tr><td colSpan={9} className="war-empty">Loading warranties…</td></tr>
            )}
            {!loading && warranties.length === 0 && (
              <tr>
                <td colSpan={9} className="war-empty">
                  <Shield size={32} color="#334155" />
                  <div>No warranties found</div>
                </td>
              </tr>
            )}
            {warranties.map((w) => (
              <WarrantyRow
                key={w.id}
                w={w}
                downloading={downloadingId === w.id}
                onOpenMachine={(serial) => navigate(`/machines/${serial}`)}
                onExtend={() => setExtendTarget(w)}
                onDownload={() => handleDownload(w)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {extendTarget && (
        <ExtendWarrantyModal
          warranty={extendTarget}
          token={access_token!}
          onClose={() => setExtendTarget(null)}
          onDone={async () => {
            setExtendTarget(null)
            setToast({ kind: 'ok', msg: 'Warranty extended' })
            await refreshAfterMutation()
          }}
        />
      )}
    </div>
  )
}

// ─── SummaryCard ──────────────────────────────────────────────────────────

function SummaryCard({
  label,
  count,
  color,
  subtitle,
  icon,
  accent,
}: {
  label: string
  count: number
  color: string
  subtitle?: string
  icon?: React.ReactNode
  accent?: boolean
}) {
  return (
    <div
      className={`war-card${accent ? ' war-card-accent' : ''}`}
      style={accent ? { borderLeft: `3px solid ${color}` } : undefined}
    >
      <div className="war-card-head">
        <span className="war-card-label">{label}</span>
        {icon}
      </div>
      <div className="war-card-count" style={{ color }}>{count}</div>
      {subtitle && <div className="war-card-sub">{subtitle}</div>}
    </div>
  )
}

// ─── WarrantyRow ──────────────────────────────────────────────────────────

function WarrantyRow({
  w,
  downloading,
  onOpenMachine,
  onExtend,
  onDownload,
}: {
  w: Warranty
  downloading: boolean
  onOpenMachine: (serial: string) => void
  onExtend: () => void
  onDownload: () => void
}) {
  const days = w.days_remaining ?? 0
  const expired = w.status === 'expired'
  const daysClass = expired
    ? 'war-days war-days-expired'
    : days <= 30
    ? 'war-days war-days-warn'
    : 'war-days war-days-ok'

  const typeClass =
    w.machine_type === 'RX' ? 'war-type-rx'
    : w.machine_type === 'RO' ? 'war-type-ro'
    : 'war-type-unknown'

  return (
    <tr className="war-row">
      <td>
        {w.serial_number ? (
          <button
            className="war-link war-mono"
            onClick={() => onOpenMachine(w.serial_number!)}
          >
            {w.serial_number}
          </button>
        ) : (
          <span className="war-mono war-muted">{w.machine_id.slice(0, 8)}</span>
        )}
      </td>
      <td>
        {w.machine_type ? (
          <span className={`war-type-badge ${typeClass}`}>{w.machine_type}</span>
        ) : '—'}
      </td>
      <td className="war-cell-customer">{w.customer_name || '—'}</td>
      <td>{formatDate(w.start_date)}</td>
      <td>{formatDate(w.end_date)}</td>
      <td className="war-mono">{w.duration_months} mo</td>
      <td className={daysClass}>
        {expired ? `${Math.abs(days)}d expired` : `${days}d`}
      </td>
      <td>
        <span className={`war-status war-status-${w.status}`}>
          {w.status.replace('_', ' ')}
        </span>
        {w.extended && <span className="war-extended-tag">Extended</span>}
      </td>
      <td className="war-cell-actions">
        <button
          className="war-btn war-btn-sm war-btn-primary"
          onClick={onExtend}
        >
          Extend
        </button>
        <button
          className="war-btn war-btn-sm war-btn-success"
          onClick={onDownload}
          disabled={downloading}
        >
          <Download size={12} />
          {downloading ? '…' : 'Cert'}
        </button>
      </td>
    </tr>
  )
}

// ─── ExtendWarrantyModal ──────────────────────────────────────────────────

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

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!reason.trim()) {
      setErr('Reason is required')
      return
    }
    if (months < 1) {
      setErr('Additional months must be at least 1')
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
    <div className="war-modal-overlay" onClick={onClose}>
      <form
        className="war-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="war-modal-title">
          Extend Warranty — {warranty.serial_number || ''}
        </h3>
        <p className="war-modal-sub">
          Currently ends {formatDate(warranty.end_date)}
          {' · '}duration {warranty.duration_months} mo
          {warranty.days_remaining != null && ` · ${warranty.days_remaining} days remaining`}
        </p>

        <label className="war-field">
          <span>Additional Months</span>
          <input
            type="number"
            min={1}
            max={60}
            value={months}
            onChange={(e) => setMonths(parseInt(e.target.value || '6', 10))}
          />
        </label>

        <label className="war-field">
          <span>Reason *</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Why is this warranty being extended?"
          />
        </label>

        <p className="war-modal-sub">
          New end date:{' '}
          <strong>
            {formatDateOnly(addMonths(new Date(warranty.end_date + 'T00:00:00'), months || 0))}
          </strong>
        </p>

        {err && <div className="war-form-error">{err}</div>}

        <div className="war-modal-actions">
          <button
            type="button"
            className="war-btn war-btn-ghost"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="war-btn war-btn-primary"
            disabled={saving}
          >
            <Plus size={14} />
            {saving ? 'Extending…' : 'Extend'}
          </button>
        </div>
      </form>
    </div>
  )
}
