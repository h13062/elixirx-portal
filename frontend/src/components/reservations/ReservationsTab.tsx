import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AlertTriangle, Calendar, ArrowUp, ArrowDown, X, Users, List } from 'lucide-react'
import { apiGet, apiPut } from '../../lib/api'
import './Reservations.css'

// ─── Types ────────────────────────────────────────────────────────────────

type ReservationStatus =
  | 'pending'
  | 'approved'
  | 'denied'
  | 'expired'
  | 'cancelled'
  | 'converted'

type ResStatusFilter = 'all' | ReservationStatus

export interface Reservation {
  id: string
  machine_id: string
  serial_number: string | null
  product_name: string | null
  reserved_by: string | null
  reserved_by_name: string | null
  reserved_for: string | null
  status: ReservationStatus
  approved_by: string | null
  approved_by_name: string | null
  deny_reason: string | null
  expires_at: string | null
  created_at: string
  updated_at: string
}

interface ExpiringSoonReservation {
  id: string
  machine_id: string
  serial_number: string | null
  reserved_by: string | null
  reserved_by_name: string | null
  reserved_for: string | null
  expires_at: string
  hours_remaining: number
}

interface AccountSummary {
  user_id: string
  full_name: string | null
  email: string | null
  tier: string | null
  total: number
  pending: number
  approved: number
  denied: number
  expired: number
  cancelled: number
  converted: number
  approval_rate: number
}

type SubView = 'all' | 'by-account'

type SortKey =
  | 'serial_number'
  | 'reserved_for'
  | 'reserved_by_name'
  | 'status'
  | 'created_at'
  | 'expires_at'
type SortDir = 'asc' | 'desc'

interface Props {
  /** Current user's UUID — used to gate "cancel" on rep-owned reservations. */
  currentUserId: string
  /** Whether the current user is admin/super_admin. */
  isAdmin: boolean
  token: string
  showToast: (message: string, type: 'success' | 'error') => void
  /** Called whenever the count of active reservations may have changed,
   *  so the parent (Inventory tab) can refresh its tab badge. */
  onActiveCountChange?: (count: number) => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────

function formatRelative(value: string): string {
  const then = new Date(value).getTime()
  const diff = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (diff < 60) return 'just now'
  if (diff < 3600) {
    const m = Math.floor(diff / 60)
    return `${m} minute${m === 1 ? '' : 's'} ago`
  }
  if (diff < 86400) {
    const h = Math.floor(diff / 3600)
    return `${h} hour${h === 1 ? '' : 's'} ago`
  }
  if (diff < 86400 * 30) {
    const d = Math.floor(diff / 86400)
    return `${d} day${d === 1 ? '' : 's'} ago`
  }
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}

interface CountdownParts {
  text: string
  /** 'green' > 24h, 'amber' < 24h, 'red' < 3h or expired */
  tone: 'green' | 'amber' | 'red'
  expired: boolean
}

function computeCountdown(expiresAt: string | null): CountdownParts {
  if (!expiresAt) return { text: '—', tone: 'green', expired: false }
  const target = new Date(expiresAt).getTime()
  const diff = target - Date.now()
  if (diff <= 0) return { text: 'Expired', tone: 'red', expired: true }

  const totalMin = Math.floor(diff / 60000)
  const days = Math.floor(totalMin / (60 * 24))
  const hours = Math.floor((totalMin % (60 * 24)) / 60)
  const minutes = totalMin % 60

  let text: string
  if (totalMin >= 60 * 24) text = `${days}d ${hours}h`
  else text = `${hours}h ${minutes}m`

  const tone: 'green' | 'amber' | 'red' =
    totalMin < 60 * 3 ? 'red'
    : totalMin < 60 * 24 ? 'amber'
    : 'green'
  return { text, tone, expired: false }
}

function deriveType(productName: string | null): 'RX' | 'RO' | null {
  if (!productName) return null
  const up = productName.toUpperCase()
  if (up.startsWith('RX')) return 'RX'
  if (up.startsWith('RO')) return 'RO'
  return null
}

// ─── Component ────────────────────────────────────────────────────────────

export default function ReservationsTab({
  currentUserId,
  isAdmin,
  token,
  showToast,
  onActiveCountChange,
}: Props) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // Honor `?status=...` from the URL on mount (set by dashboard cards / quick
  // actions). Only the values produced by the status-filter tabs themselves
  // are accepted — anything else falls back to 'all'.
  const initialStatusFilter: ResStatusFilter = useMemo(() => {
    const s = searchParams.get('status')
    if (s === 'pending' || s === 'approved' || s === 'denied'
        || s === 'expired' || s === 'cancelled' || s === 'converted') {
      return s
    }
    return 'all'
    // initial value is captured once — re-applying on every URL change is the
    // parent's job (Inventory page reloads ReservationsTab when activeTab flips)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [list, setList] = useState<Reservation[]>([])
  const [expiring, setExpiring] = useState<ExpiringSoonReservation[]>([])
  const [accounts, setAccounts] = useState<AccountSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<ResStatusFilter>(initialStatusFilter)

  // Sub-view: All Reservations vs By Account
  const [subView, setSubView] = useState<SubView>('all')

  // Rep filter (user_id) — applied client-side to the All Reservations table
  const [repFilter, setRepFilter] = useState<string | null>(null)

  // Sorting
  const [sortKey, setSortKey] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  // Action state
  const [pendingApproveId, setPendingApproveId] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [denyTarget, setDenyTarget] = useState<Reservation | null>(null)
  const [cancelTarget, setCancelTarget] = useState<Reservation | null>(null)

  // Forces the countdown column to re-render every minute
  const [, setNowTick] = useState(0)
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ─── Fetch ──────────────────────────────────────────────────────────────

  const fetchAll = useCallback(async () => {
    setError(null)
    try {
      const [items, exp, byAccount] = await Promise.all([
        apiGet<Reservation[]>('/api/reservations', token),
        apiGet<ExpiringSoonReservation[]>('/api/reservations/expiring-soon', token),
        apiGet<{ accounts: AccountSummary[] }>('/api/reservations/by-account', token)
          .catch((e) => {
            // Endpoint failure shouldn't block the All Reservations view.
            console.error('by-account fetch error:', e)
            return { accounts: [] }
          }),
      ])
      setList(items)
      setExpiring(exp)
      setAccounts(byAccount.accounts)
    } catch (e) {
      setError((e as Error).message || 'Failed to load reservations')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [token])

  useEffect(() => {
    setRefreshing(true)
    fetchAll()
  }, [fetchAll])

  // Live countdown refresh — every 60s.
  useEffect(() => {
    tickRef.current = setInterval(() => setNowTick(t => t + 1), 60_000)
    return () => {
      if (tickRef.current) clearInterval(tickRef.current)
    }
  }, [])

  // Notify parent of active count whenever the list changes.
  useEffect(() => {
    if (!onActiveCountChange) return
    const active = list.filter(r => r.status === 'pending' || r.status === 'approved').length
    onActiveCountChange(active)
  }, [list, onActiveCountChange])

  // ─── Derived ────────────────────────────────────────────────────────────

  const counts = useMemo(() => {
    const c = {
      all: list.length,
      pending: 0, approved: 0, denied: 0, expired: 0, cancelled: 0, converted: 0,
    }
    for (const r of list) {
      if (r.status in c) (c as Record<string, number>)[r.status]++
    }
    return c
  }, [list])

  // Reps observed in the data (used by the dropdown). Each entry carries a
  // count of that rep's reservations so the dropdown can show e.g. "Minh (4)".
  const repOptions = useMemo(() => {
    const map = new Map<string, { user_id: string; name: string; count: number }>()
    for (const r of list) {
      if (!r.reserved_by) continue
      const cur = map.get(r.reserved_by)
      if (cur) {
        cur.count++
      } else {
        map.set(r.reserved_by, {
          user_id: r.reserved_by,
          name: r.reserved_by_name || r.reserved_by.slice(0, 8),
          count: 1,
        })
      }
    }
    return Array.from(map.values()).sort((a, b) => b.count - a.count)
  }, [list])

  const repFilterName = useMemo(() => {
    if (!repFilter) return null
    return repOptions.find(o => o.user_id === repFilter)?.name ?? null
  }, [repFilter, repOptions])

  const filteredList = useMemo(() => {
    let out = list
    if (filter !== 'all') out = out.filter(r => r.status === filter)
    if (repFilter) out = out.filter(r => r.reserved_by === repFilter)
    return out
  }, [list, filter, repFilter])

  const sortedList = useMemo(() => {
    const arr = filteredList.slice()
    const dir = sortDir === 'asc' ? 1 : -1
    arr.sort((a, b) => {
      const av = (a[sortKey] as string | null) ?? ''
      const bv = (b[sortKey] as string | null) ?? ''
      // Date columns: compare as timestamps so "Jan 2026" < "Mar 2026" works
      // even though both are ISO strings (the lexicographic order matches, but
      // Date parsing also tolerates nulls/empties cleanly).
      if (sortKey === 'created_at' || sortKey === 'expires_at') {
        const at = av ? new Date(av).getTime() : 0
        const bt = bv ? new Date(bv).getTime() : 0
        return (at - bt) * dir
      }
      return av.localeCompare(bv) * dir
    })
    return arr
  }, [filteredList, sortKey, sortDir])

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      // First click on a date column defaults to descending (newest first);
      // first click on a text column defaults to ascending (A-Z).
      setSortDir(key === 'created_at' || key === 'expires_at' ? 'desc' : 'asc')
    }
  }

  // ─── Actions ────────────────────────────────────────────────────────────

  async function handleApprove(r: Reservation) {
    setBusyId(r.id)
    try {
      await apiPut(`/api/reservations/${r.id}/approve`, {}, token)
      showToast('Reservation approved! 7-day countdown started.', 'success')
      setPendingApproveId(null)
      setRefreshing(true)
      await fetchAll()
    } catch (e) {
      showToast((e as Error).message || 'Approve failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  async function handleDenySubmit(r: Reservation, reason: string) {
    setBusyId(r.id)
    try {
      await apiPut(`/api/reservations/${r.id}/deny`, { reason }, token)
      showToast('Reservation denied.', 'success')
      setDenyTarget(null)
      setRefreshing(true)
      await fetchAll()
    } catch (e) {
      showToast((e as Error).message || 'Deny failed', 'error')
      throw e
    } finally {
      setBusyId(null)
    }
  }

  async function handleCancel(r: Reservation) {
    setBusyId(r.id)
    try {
      await apiPut(`/api/reservations/${r.id}/cancel`, {}, token)
      showToast('Reservation cancelled.', 'success')
      setCancelTarget(null)
      setRefreshing(true)
      await fetchAll()
    } catch (e) {
      showToast((e as Error).message || 'Cancel failed', 'error')
    } finally {
      setBusyId(null)
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="rsv-error-banner">
        <AlertTriangle size={16} />
        <span>{error}</span>
        <button
          className="rsv-error-retry"
          onClick={() => { setRefreshing(true); fetchAll() }}
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="rsv-tab">
      {/* ── Summary cards ────────────────────────────────────────── */}
      <div className="rsv-summary-row">
        <SummaryCard
          label="PENDING APPROVAL"
          count={counts.pending}
          color="#F59E0B"
          accent
        />
        <SummaryCard
          label="APPROVED (ACTIVE)"
          count={counts.approved}
          color="#10B981"
          subtitle="with countdown"
          accent
        />
        <SummaryCard
          label="ALL TIME"
          count={counts.all}
          color="#F8FAFC"
          subtitle={`${counts.denied} denied · ${counts.expired} expired · ${counts.cancelled} cancelled`}
        />
      </div>

      {/* ── Expiring soon alert ──────────────────────────────────── */}
      {expiring.length > 0 && (
        <div className="rsv-expiring-alert">
          <div className="rsv-expiring-header">
            <AlertTriangle size={16} color="#F59E0B" />
            <span>Reservations expiring within 24 hours</span>
          </div>
          <div className="rsv-expiring-list">
            {expiring.map((e) => (
              <div className="rsv-expiring-row" key={e.id}>
                <button
                  className="rsv-link rsv-mono"
                  onClick={() => e.serial_number && navigate(`/machines/${e.serial_number}`)}
                  disabled={!e.serial_number}
                >
                  {e.serial_number || e.machine_id.slice(0, 8)}
                </button>
                <span className="rsv-expiring-for">{e.reserved_for || '—'}</span>
                <span className="rsv-expiring-by">{e.reserved_by_name || '—'}</span>
                <span className="rsv-expiring-hours">
                  {e.hours_remaining}h remaining
                </span>
                <button
                  className="rsv-btn rsv-btn-xs rsv-btn-ghost"
                  onClick={() => {
                    const r = list.find(x => x.id === e.id)
                    if (r) setCancelTarget(r)
                  }}
                  disabled={busyId === e.id}
                >
                  Cancel
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Sub-view tabs (All Reservations | By Account) ────────── */}
      <div className="rsv-subtabs">
        <button
          className={`rsv-subtab${subView === 'all' ? ' rsv-subtab-active' : ''}`}
          onClick={() => setSubView('all')}
        >
          <List size={13} /> All Reservations
        </button>
        <button
          className={`rsv-subtab${subView === 'by-account' ? ' rsv-subtab-active' : ''}`}
          onClick={() => setSubView('by-account')}
        >
          <Users size={13} /> By Account
          {accounts.length > 0 && (
            <span className="rsv-subtab-count">{accounts.length}</span>
          )}
        </button>
      </div>

      {subView === 'by-account' ? (
        <ByAccountView
          accounts={accounts}
          loading={loading}
          onView={(uid) => {
            setRepFilter(uid)
            setFilter('all')
            setSubView('all')
          }}
        />
      ) : (
        <>
          {/* ── Status filter tabs ─────────────────────────────────── */}
          <div className="rsv-filter-bar">
            {(['all', 'pending', 'approved', 'denied', 'expired', 'cancelled'] as ResStatusFilter[]).map((s) => (
              <button
                key={s}
                className={`rsv-tab-btn${filter === s ? ' rsv-tab-active' : ''}`}
                onClick={() => setFilter(s)}
              >
                {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)} ({counts[s as keyof typeof counts]})
              </button>
            ))}
          </div>

          {/* ── Rep filter dropdown ─────────────────────────────── */}
          <div className="rsv-rep-filter">
            <label className="rsv-rep-filter-label">Filter by Rep</label>
            <select
              className="rsv-rep-filter-select"
              value={repFilter ?? ''}
              onChange={(e) => setRepFilter(e.target.value || null)}
            >
              <option value="">All Reps ({list.length})</option>
              {repOptions.map(o => (
                <option key={o.user_id} value={o.user_id}>
                  {o.name} ({o.count})
                </option>
              ))}
            </select>
            {repFilter && (
              <button
                className="rsv-rep-clear"
                onClick={() => setRepFilter(null)}
                title="Clear rep filter"
              >
                <X size={12} />
              </button>
            )}
          </div>

          <div className="rsv-count-line">
            {repFilterName ? (
              <>
                Showing <strong>{sortedList.length}</strong> reservation{sortedList.length === 1 ? '' : 's'} by{' '}
                <strong>{repFilterName}</strong>
              </>
            ) : (
              <>
                Showing <strong>{sortedList.length}</strong> of {list.length} reservation{list.length === 1 ? '' : 's'}
              </>
            )}
            {refreshing && <span className="rsv-refresh-dot"> · refreshing…</span>}
          </div>

          {/* ── Table ────────────────────────────────────────────── */}
          <div className="rsv-table-wrap">
            <table className="rsv-table">
              <thead>
                <tr>
                  <SortableTh label="Machine S/N" col="serial_number" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
                  <th>Type</th>
                  <SortableTh label="Reserved For" col="reserved_for" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
                  <SortableTh label="Requested By" col="reserved_by_name" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
                  <SortableTh label="Status" col="status" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
                  <SortableTh label="Requested" col="created_at" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
                  <SortableTh label="Expires" col="expires_at" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
                  <th className="rsv-th-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading && sortedList.length === 0 && (
                  <tr><td colSpan={8} className="rsv-empty">Loading reservations…</td></tr>
                )}
                {!loading && sortedList.length === 0 && (
                  <tr>
                    <td colSpan={8} className="rsv-empty">
                      <Calendar size={28} color="#334155" />
                      <div>No reservations found</div>
                    </td>
                  </tr>
                )}
                {sortedList.map((r) => (
                  <ReservationRow
                    key={r.id}
                    r={r}
                    isAdmin={isAdmin}
                    isOwner={r.reserved_by === currentUserId}
                    pendingApproveId={pendingApproveId}
                    busyId={busyId}
                    onOpenMachine={(serial) => navigate(`/machines/${serial}`)}
                    onApproveAsk={() => setPendingApproveId(r.id)}
                    onApproveCancel={() => setPendingApproveId(null)}
                    onApproveConfirm={() => handleApprove(r)}
                    onDenyOpen={() => setDenyTarget(r)}
                    onCancelOpen={() => setCancelTarget(r)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Modals ───────────────────────────────────────────────── */}
      {denyTarget && (
        <DenyReservationModal
          reservation={denyTarget}
          saving={busyId === denyTarget.id}
          onClose={() => setDenyTarget(null)}
          onSubmit={(reason) => handleDenySubmit(denyTarget, reason)}
        />
      )}
      {cancelTarget && (
        <CancelReservationModal
          saving={busyId === cancelTarget.id}
          onCancel={() => setCancelTarget(null)}
          onConfirm={() => handleCancel(cancelTarget)}
        />
      )}
    </div>
  )
}

// ─── Sortable column header ───────────────────────────────────────────────

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
      className={`rsv-th-sortable${active ? ' rsv-th-active' : ''}`}
      onClick={() => onClick(col)}
    >
      <span className="rsv-th-inner">
        {label}
        {active && (
          sortDir === 'asc'
            ? <ArrowUp size={11} />
            : <ArrowDown size={11} />
        )}
      </span>
    </th>
  )
}

// ─── ByAccountView ────────────────────────────────────────────────────────

function ByAccountView({
  accounts,
  loading,
  onView,
}: {
  accounts: AccountSummary[]
  loading: boolean
  onView: (userId: string) => void
}) {
  if (loading && accounts.length === 0) {
    return <div className="rsv-empty rsv-by-account-loading">Loading account summary…</div>
  }
  if (!loading && accounts.length === 0) {
    return (
      <div className="rsv-empty rsv-by-account-empty">
        <Users size={28} color="#334155" />
        <div>No reservations recorded yet</div>
      </div>
    )
  }
  return (
    <div className="rsv-account-grid">
      {accounts.map(a => (
        <AccountCard key={a.user_id} a={a} onView={() => onView(a.user_id)} />
      ))}
    </div>
  )
}

function AccountCard({ a, onView }: { a: AccountSummary; onView: () => void }) {
  const tier = (a.tier || '').toLowerCase()
  const tierClass =
    tier === 'distributor' ? 'rsv-tier-distributor'
    : tier === 'agent' ? 'rsv-tier-agent'
    : tier === 'master_agent' ? 'rsv-tier-master'
    : 'rsv-tier-unknown'
  const rate = a.approval_rate
  const rateClass =
    rate > 70 ? 'rsv-rate-good'
    : rate >= 40 ? 'rsv-rate-warn'
    : 'rsv-rate-bad'

  return (
    <div className="rsv-account-card">
      <div className="rsv-account-card-head">
        <div>
          <div className="rsv-account-name">{a.full_name || '—'}</div>
          <div className="rsv-account-email">{a.email || '—'}</div>
        </div>
        {a.tier && (
          <span className={`rsv-tier-badge ${tierClass}`}>
            {a.tier.replace('_', ' ')}
          </span>
        )}
      </div>

      <div className="rsv-account-stats">
        <Stat label="Total"     value={a.total}     toneClass="rsv-stat-total" />
        <Stat label="Approval"  value={`${rate}%`}  toneClass={rateClass} />
        <Stat label="Pending"   value={a.pending}   toneClass="rsv-stat-pending" />
        <Stat label="Approved"  value={a.approved}  toneClass="rsv-stat-approved" />
        <Stat label="Denied"    value={a.denied}    toneClass="rsv-stat-denied" />
        <Stat label="Expired"   value={a.expired}   toneClass="rsv-stat-expired" />
      </div>

      <button
        className="rsv-btn rsv-btn-sm rsv-btn-ghost rsv-account-view-btn"
        onClick={onView}
      >
        View Reservations
      </button>
    </div>
  )
}

function Stat({
  label,
  value,
  toneClass,
}: {
  label: string
  value: number | string
  toneClass: string
}) {
  return (
    <div className="rsv-account-stat">
      <span className="rsv-account-stat-label">{label}</span>
      <span className={`rsv-account-stat-value ${toneClass}`}>{value}</span>
    </div>
  )
}

// ─── SummaryCard ──────────────────────────────────────────────────────────

function SummaryCard({
  label,
  count,
  color,
  subtitle,
  accent,
}: {
  label: string
  count: number
  color: string
  subtitle?: string
  accent?: boolean
}) {
  return (
    <div
      className={`rsv-card${accent ? ' rsv-card-accent' : ''}`}
      style={accent ? { borderLeft: `3px solid ${color}` } : undefined}
    >
      <div className="rsv-card-label">{label}</div>
      <div className="rsv-card-count" style={{ color }}>{count}</div>
      {subtitle && <div className="rsv-card-sub">{subtitle}</div>}
    </div>
  )
}

// ─── ReservationRow ───────────────────────────────────────────────────────

function ReservationRow({
  r,
  isAdmin,
  isOwner,
  pendingApproveId,
  busyId,
  onOpenMachine,
  onApproveAsk,
  onApproveCancel,
  onApproveConfirm,
  onDenyOpen,
  onCancelOpen,
}: {
  r: Reservation
  isAdmin: boolean
  isOwner: boolean
  pendingApproveId: string | null
  busyId: string | null
  onOpenMachine: (serial: string) => void
  onApproveAsk: () => void
  onApproveCancel: () => void
  onApproveConfirm: () => void
  onDenyOpen: () => void
  onCancelOpen: () => void
}) {
  const type = deriveType(r.product_name)
  const cd = computeCountdown(r.expires_at)
  const showCountdown = r.status === 'approved'
  const askingApprove = pendingApproveId === r.id
  const isBusy = busyId === r.id

  return (
    <tr className="rsv-row">
      <td>
        {r.serial_number ? (
          <button
            className="rsv-link rsv-mono"
            onClick={() => onOpenMachine(r.serial_number!)}
          >
            {r.serial_number}
          </button>
        ) : (
          <span className="rsv-mono rsv-muted">{r.machine_id.slice(0, 8)}</span>
        )}
      </td>
      <td>
        {type ? (
          <span className={`rsv-type-badge rsv-type-${type.toLowerCase()}`}>{type}</span>
        ) : '—'}
      </td>
      <td className="rsv-cell-for">{r.reserved_for || '—'}</td>
      <td className="rsv-cell-by">{r.reserved_by_name || '—'}</td>
      <td>
        <span className={`rsv-status rsv-status-${r.status}`}>
          {r.status}
        </span>
      </td>
      <td className="rsv-cell-rel">{formatRelative(r.created_at)}</td>
      <td>
        {showCountdown ? (
          <span className={`rsv-countdown rsv-countdown-${cd.tone}`}>
            {cd.expired ? cd.text : `${cd.text} remaining`}
          </span>
        ) : (
          <span className="rsv-muted">—</span>
        )}
      </td>
      <td className="rsv-cell-actions">
        {/* PENDING — admin sees Approve / Deny; owner sees Cancel */}
        {r.status === 'pending' && isAdmin && (
          askingApprove ? (
            <span className="rsv-inline-confirm">
              Approve for {r.reserved_for || '—'}?
              <button
                className="rsv-btn rsv-btn-xs rsv-btn-ghost"
                onClick={onApproveCancel}
                disabled={isBusy}
              >
                No
              </button>
              <button
                className="rsv-btn rsv-btn-xs rsv-btn-success"
                onClick={onApproveConfirm}
                disabled={isBusy}
              >
                {isBusy ? '…' : 'Yes'}
              </button>
            </span>
          ) : (
            <>
              <button
                className="rsv-btn rsv-btn-sm rsv-btn-success"
                onClick={onApproveAsk}
                disabled={isBusy}
              >
                Approve
              </button>
              <button
                className="rsv-btn rsv-btn-sm rsv-btn-danger"
                onClick={onDenyOpen}
                disabled={isBusy}
              >
                Deny
              </button>
            </>
          )
        )}
        {r.status === 'pending' && !isAdmin && isOwner && (
          <button
            className="rsv-btn rsv-btn-sm rsv-btn-ghost"
            onClick={onCancelOpen}
            disabled={isBusy}
          >
            Cancel
          </button>
        )}

        {/* APPROVED — admin or owner can cancel */}
        {r.status === 'approved' && (isAdmin || isOwner) && (
          <button
            className="rsv-btn rsv-btn-sm rsv-btn-ghost"
            onClick={onCancelOpen}
            disabled={isBusy}
          >
            Cancel
          </button>
        )}
      </td>
    </tr>
  )
}

// ─── Modals ───────────────────────────────────────────────────────────────

function DenyReservationModal({
  reservation,
  saving,
  onClose,
  onSubmit,
}: {
  reservation: Reservation
  saving: boolean
  onClose: () => void
  onSubmit: (reason: string) => Promise<void>
}) {
  const [reason, setReason] = useState('')
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!reason.trim()) {
      setErr('Reason is required')
      return
    }
    try {
      setErr(null)
      await onSubmit(reason.trim())
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  return (
    <div className="rsv-modal-overlay" onClick={onClose}>
      <form
        className="rsv-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 className="rsv-modal-title">Deny Reservation</h3>
        <p className="rsv-modal-sub">
          Machine <strong>{reservation.serial_number || '—'}</strong>{' '}
          requested by <strong>{reservation.reserved_by_name || '—'}</strong>{' '}
          for <strong>{reservation.reserved_for || '—'}</strong>
        </p>
        <label className="rsv-field">
          <span>Reason *</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Why is this reservation being denied?"
            autoFocus
          />
        </label>
        {err && <div className="rsv-form-error">{err}</div>}
        <div className="rsv-modal-actions">
          <button
            type="button"
            className="rsv-btn rsv-btn-ghost"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="rsv-btn rsv-btn-danger"
            disabled={saving}
          >
            {saving ? 'Denying…' : 'Deny Reservation'}
          </button>
        </div>
      </form>
    </div>
  )
}

function CancelReservationModal({
  saving,
  onCancel,
  onConfirm,
}: {
  saving: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div className="rsv-modal-overlay" onClick={onCancel}>
      <div
        className="rsv-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="rsv-modal-title">Cancel Reservation</h3>
        <p className="rsv-modal-sub">
          Cancel this reservation? The machine will become available again.
        </p>
        <div className="rsv-modal-actions">
          <button
            className="rsv-btn rsv-btn-ghost"
            onClick={onCancel}
            disabled={saving}
          >
            Keep Reservation
          </button>
          <button
            className="rsv-btn rsv-btn-danger"
            onClick={onConfirm}
            disabled={saving}
          >
            {saving ? 'Cancelling…' : 'Yes, Cancel'}
          </button>
        </div>
      </div>
    </div>
  )
}
