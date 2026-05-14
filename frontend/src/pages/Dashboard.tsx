import { useEffect, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Package,
  PackageCheck,
  Shield,
  ShieldCheck,
  AlertTriangle,
  Activity,
  CheckCircle,
  Clock,
  Plus,
  CalendarCheck,
  Beaker,
  Zap,
  ListChecks,
  Eye,
  ArrowRight,
  Download,
  ChevronDown,
  ChevronRight as ChevronRightIcon,
} from 'lucide-react'
import { useAuth } from '../lib/auth'
import { apiGet, apiPut } from '../lib/api'
import { downloadWarrantyCertificate } from '../lib/download'
import ExtendWarrantyModal from '../components/ExtendWarrantyModal'
import './Dashboard.css'

// ─── Types (mirror backend dashboard_models.py) ───────────────────────────

interface MachineCounts {
  total: number
  available: number
  reserved: number
  ordered: number
  sold: number
  delivered: number
  returned: number
}

interface WarrantyCounts {
  active: number
  expiring_soon: number
  expired: number
  total: number
}

interface IssueCounts {
  open: number
  in_progress: number
  resolved: number
  closed: number
  urgent: number
  high: number
  total: number
}

interface ReservationCounts {
  pending: number
  approved: number
  denied: number
  expired: number
  cancelled: number
  converted: number
  total: number
}

interface LowStockItem {
  product_id: string
  product_name: string
  sku: string | null
  quantity: number
  min_threshold: number
}

interface RecentActivityEntry {
  id: string
  machine_id: string
  serial_number: string | null
  from_status: string | null
  to_status: string
  changed_by: string | null
  changed_by_name: string | null
  reason: string | null
  created_at: string
}

interface ExpiringWarrantyEntry {
  warranty_id: string
  machine_id: string
  serial_number: string | null
  machine_type: string | null
  customer_name: string | null
  end_date: string
  duration_months: number
  days_remaining: number
}

interface ExpiredWarrantyEntry {
  warranty_id: string
  machine_id: string
  serial_number: string | null
  machine_type: string | null
  customer_name: string | null
  end_date: string
  days_overdue: number
}

interface RecentIssueEntry {
  id: string
  machine_id: string
  serial_number: string | null
  machine_serial: string | null
  machine_type: string | null
  title: string
  priority: string
  status: string
  reported_by: string | null
  reported_by_name: string | null
  created_at: string
}

interface DashboardSummary {
  machines: MachineCounts
  warranties: WarrantyCounts
  issues: IssueCounts
  reservations: ReservationCounts
  low_stock: { count: number; total_tracked: number; items: LowStockItem[] }
  recent_activity: RecentActivityEntry[]
  recent_issues: RecentIssueEntry[]
  open_issues: RecentIssueEntry[]
  expiring_warranties: ExpiringWarrantyEntry[]
  expired_warranties: ExpiredWarrantyEntry[]
}

// ─── Helpers ──────────────────────────────────────────────────────────────

function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

function formatToday(): string {
  return new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

function formatRelative(value: string): string {
  const then = new Date(value).getTime()
  const diff = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric',
  })
}

function truncate(s: string, max: number): string {
  return s.length <= max ? s : s.slice(0, max - 1) + '…'
}

/** Status-name → dot color, for the Recent Activity feed. */
function statusDotColor(s: string): string {
  switch (s) {
    case 'available': return '#10B981'
    case 'reserved':  return '#F59E0B'
    case 'ordered':   return '#8B5CF6'
    case 'sold':      return '#3B82F6'
    case 'delivered': return '#10B981'
    case 'returned':  return '#EF4444'
    default:          return '#64748B'
  }
}

/** Derive RX/RO machine type from a serial-number prefix. */
function machineTypeFromSerial(serial: string | null | undefined): string | null {
  if (!serial) return null
  const upper = serial.toUpperCase()
  if (upper.startsWith('RX')) return 'RX'
  if (upper.startsWith('RO')) return 'RO'
  return null
}

/** Full local datetime for hover tooltips. */
function formatFullDateTime(value: string): string {
  return new Date(value).toLocaleString('en-US', {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** A consumable is treated as a "filter" if its product name mentions filter. */
function isFilterProduct(productName: string): boolean {
  return productName.toLowerCase().includes('filter')
}

// ─── Component ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { user, access_token } = useAuth()
  const navigate = useNavigate()

  const isRep = user?.role === 'rep'
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'

  const [data, setData] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null)

  // Toast auto-dismiss
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])

  const showToast = useCallback(
    (kind: 'ok' | 'err', msg: string) => setToast({ kind, msg }),
    [],
  )

  const fetchSummary = useCallback(async () => {
    if (!access_token) return
    setError(null)
    try {
      const d = await apiGet<DashboardSummary>('/api/dashboard/summary', access_token)
      setData(d)
    } catch (e) {
      setError((e as Error).message || 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }, [access_token])

  useEffect(() => {
    fetchSummary()
  }, [fetchSummary])

  const greeting = useMemo(() => getGreeting(), [])
  const today = useMemo(() => formatToday(), [])

  return (
    <div className="dash-page">
      <header className="dash-greeting">
        <div className="dash-greeting-line">
          {greeting},{' '}
          <strong>{user?.full_name || 'there'}</strong>
        </div>
        <div className="dash-greeting-sub">{today}</div>
      </header>

      {error && (
        <div className="dash-error-banner">
          <AlertTriangle size={16} />
          <span>{error}</span>
          <button
            className="dash-error-retry"
            onClick={() => { setLoading(true); fetchSummary() }}
          >
            Retry
          </button>
        </div>
      )}

      {toast && (
        <div className={`dash-toast dash-toast-${toast.kind}`}>{toast.msg}</div>
      )}

      {isRep
        ? <RepView data={data} loading={loading} navigate={navigate} />
        : <AdminView
            data={data}
            loading={loading}
            navigate={navigate}
            isAdmin={isAdmin}
            onRefresh={fetchSummary}
            showToast={showToast}
          />
      }
    </div>
  )
}

// ─── ADMIN VIEW ───────────────────────────────────────────────────────────

function AdminView({
  data,
  loading,
  navigate,
  isAdmin,
  onRefresh,
  showToast,
}: {
  data: DashboardSummary | null
  loading: boolean
  navigate: ReturnType<typeof useNavigate>
  isAdmin: boolean
  onRefresh: () => void
  showToast: (kind: 'ok' | 'err', msg: string) => void
}) {
  const m = data?.machines
  const w = data?.warranties
  const i = data?.issues
  const r = data?.reservations
  const ls = data?.low_stock

  const issuesActive = (i?.open ?? 0) + (i?.in_progress ?? 0)
  const issuesColor =
    (i?.urgent ?? 0) > 0 ? '#EF4444'
    : (i?.high ?? 0) > 0 ? '#F59E0B'
    : '#3B82F6'

  const lowStockCount = ls?.count ?? 0
  const expiringSoon = w?.expiring_soon ?? 0

  return (
    <>
      {/* ── Summary cards (5) ──────────────────────────────────── */}
      <div className="dash-cards-row">
        <SummaryCard
          loading={loading}
          icon={<Package size={18} color="#3B82F6" />}
          label="TOTAL MACHINES"
          count={m?.total ?? 0}
          color="#F8FAFC"
          subtitle={
            <span style={{ color: '#10B981' }}>
              {m?.available ?? 0} available
            </span>
          }
          onClick={() => navigate('/inventory?tab=machines')}
        />
        <SummaryCard
          loading={loading}
          icon={<Shield size={18} color="#10B981" />}
          label="ACTIVE WARRANTIES"
          count={w?.active ?? 0}
          color="#10B981"
          subtitle={
            expiringSoon > 0
              ? <span style={{ color: '#F59E0B' }}>{expiringSoon} expiring soon</span>
              : <span style={{ color: '#64748B' }}>all good</span>
          }
          onClick={() =>
            navigate(
              expiringSoon > 0 ? '/warranty?status=expiring_soon' : '/warranty'
            )
          }
        />
        <SummaryCard
          loading={loading}
          icon={<AlertTriangle size={18} color={issuesColor} />}
          label="OPEN ISSUES"
          count={issuesActive}
          color={issuesColor}
          subtitle={
            (i?.urgent ?? 0) > 0
              ? <span style={{ color: '#EF4444' }}>{i?.urgent} urgent</span>
              : <span style={{ color: '#64748B' }}>—</span>
          }
          onClick={() => navigate('/issues?status=open')}
        />
        <SummaryCard
          loading={loading}
          icon={<Clock size={18} color="#F59E0B" />}
          label="PENDING APPROVAL"
          count={r?.pending ?? 0}
          color="#F59E0B"
          subtitle={
            <span style={{ color: '#10B981' }}>
              {r?.approved ?? 0} active
            </span>
          }
          onClick={() => navigate('/inventory?tab=reservations&status=pending')}
        />
        <SummaryCard
          loading={loading}
          icon={
            <AlertTriangle
              size={18}
              color={lowStockCount > 0 ? '#EF4444' : '#10B981'}
            />
          }
          label="LOW STOCK ITEMS"
          count={lowStockCount}
          color={lowStockCount > 0 ? '#EF4444' : '#10B981'}
          subtitle={
            lowStockCount === 0
              ? <span style={{ color: '#64748B' }}>all stocked</span>
              : <span style={{ color: '#EF4444' }}>{lowStockCount} need restocking</span>
          }
          onClick={() => navigate('/inventory?tab=consumables&alert=low_stock')}
        />
      </div>

      {/* ── Two-column layout ──────────────────────────────────── */}
      <div className="dash-columns">
        <div className="dash-col-left">
          <WarrantyExpiringAlert
            items={data?.expiring_warranties ?? []}
            count={expiringSoon}
            activeCount={w?.active ?? 0}
            isAdmin={isAdmin}
            onRefresh={onRefresh}
            showToast={showToast}
            navigate={navigate}
          />
          <ExpiredWarrantiesSection
            items={data?.expired_warranties ?? []}
            count={w?.expired ?? 0}
            navigate={navigate}
          />
          <LowStockAlert
            items={data?.low_stock?.items ?? []}
            count={data?.low_stock?.count ?? 0}
            totalTracked={data?.low_stock?.total_tracked ?? 0}
            navigate={navigate}
          />
          <RecentActivitySection
            items={data?.recent_activity ?? []}
            navigate={navigate}
          />
        </div>
        <div className="dash-col-right">
          <IssueTrackerWidget
            items={data?.open_issues ?? data?.recent_issues ?? []}
            counts={i}
            isAdmin={isAdmin}
            navigate={navigate}
            onRefresh={onRefresh}
            showToast={showToast}
          />
          <QuickActions
            actions={[
              { label: 'Register Machine', icon: <Plus size={14} />, to: '/inventory?tab=machines' },
              { label: 'Check Warranties', icon: <Shield size={14} />, to: '/warranty' },
              { label: 'View Reservations', icon: <CalendarCheck size={14} />, to: '/inventory?tab=reservations' },
              { label: 'Manage Stock', icon: <Beaker size={14} />, to: '/inventory?tab=consumables' },
            ]}
            navigate={navigate}
          />
        </div>
      </div>
    </>
  )
}

// ─── REP VIEW ─────────────────────────────────────────────────────────────

function RepView({
  data,
  loading,
  navigate,
}: {
  data: DashboardSummary | null
  loading: boolean
  navigate: ReturnType<typeof useNavigate>
}) {
  const r = data?.reservations
  const i = data?.issues
  const m = data?.machines

  const myActive = (r?.pending ?? 0) + (r?.approved ?? 0)
  const myIssues = (i?.open ?? 0) + (i?.in_progress ?? 0)

  return (
    <>
      <div className="dash-cards-row">
        <SummaryCard
          loading={loading}
          icon={<CalendarCheck size={18} color="#3B82F6" />}
          label="MY RESERVATIONS"
          count={myActive}
          color="#F8FAFC"
          subtitle={
            <span style={{ color: '#94A3B8' }}>
              <span style={{ color: '#F59E0B' }}>{r?.pending ?? 0} pending</span>
              {' · '}
              <span style={{ color: '#10B981' }}>{r?.approved ?? 0} active</span>
            </span>
          }
          onClick={() => navigate('/inventory?tab=reservations')}
        />
        <SummaryCard
          loading={loading}
          icon={<AlertTriangle size={18} color="#F59E0B" />}
          label="MY ISSUES"
          count={myIssues}
          color="#F59E0B"
          subtitle={
            <span style={{ color: '#10B981' }}>
              {i?.resolved ?? 0} resolved
            </span>
          }
          onClick={() => navigate('/inventory?tab=machines&show=issues')}
        />
        <SummaryCard
          loading={loading}
          icon={<Package size={18} color="#10B981" />}
          label="AVAILABLE MACHINES"
          count={m?.available ?? 0}
          color="#10B981"
          subtitle={<span style={{ color: '#64748B' }}>across all types</span>}
          onClick={() => navigate('/inventory?tab=machines&status=available')}
        />
      </div>

      <QuickActions
        actions={[
          { label: 'Reserve Machine', icon: <CalendarCheck size={14} />, to: '/inventory?tab=machines&status=available' },
          { label: 'Report Issue', icon: <AlertTriangle size={14} />, to: '/inventory?tab=machines' },
          { label: 'My Reservations', icon: <ListChecks size={14} />, to: '/inventory?tab=reservations' },
          { label: 'Browse Inventory', icon: <Eye size={14} />, to: '/inventory' },
        ]}
        navigate={navigate}
        wide
      />
    </>
  )
}

// ─── Alert sections ───────────────────────────────────────────────────────

/** Pick a color for the days-remaining number. */
function daysRemainingTone(days: number): 'amber' | 'orange' | 'red' {
  if (days < 7) return 'red'
  if (days <= 14) return 'orange'
  return 'amber'
}

interface ExtendTarget {
  warrantyId: string
  serialNumber: string
  currentEndDate: string
  currentDuration: number
  daysRemaining: number
}

function WarrantyExpiringAlert({
  items,
  count,
  activeCount,
  isAdmin,
  onRefresh,
  showToast,
  navigate,
}: {
  items: ExpiringWarrantyEntry[]
  count: number
  activeCount: number
  isAdmin: boolean
  onRefresh: () => void
  showToast: (kind: 'ok' | 'err', msg: string) => void
  navigate: ReturnType<typeof useNavigate>
}) {
  const [extendTarget, setExtendTarget] = useState<ExtendTarget | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)

  // Empty state — small green "all good" card.
  if (count === 0 || items.length === 0) {
    return (
      <section className="dash-warranty-ok">
        <ShieldCheck size={20} color="#10B981" />
        <div className="dash-warranty-ok-body">
          <div className="dash-warranty-ok-title">
            All warranties are in good standing
          </div>
          <div className="dash-warranty-ok-sub">
            {activeCount} active {activeCount === 1 ? 'warranty' : 'warranties'}
          </div>
        </div>
      </section>
    )
  }

  const visible = items.slice(0, 5)
  const remaining = Math.max(0, count - visible.length)
  const hasCritical = visible.some(w => w.days_remaining < 7)

  const handleDownload = async (w: ExpiringWarrantyEntry) => {
    setDownloadingId(w.warranty_id)
    const ok = await downloadWarrantyCertificate(
      w.serial_number || w.machine_id,
      w.serial_number,
    )
    setDownloadingId(null)
    if (ok) showToast('ok', 'Certificate downloaded')
    else showToast('err', 'Download failed')
  }

  return (
    <>
      <section className="dash-warranty-alert">
        <div className="dash-warranty-alert-head">
          <span className="dash-warranty-alert-title">
            <AlertTriangle size={14} color="#F59E0B" />
            {count} {count === 1 ? 'Warranty' : 'Warranties'} Expiring Soon
            {hasCritical && <span className="dash-pulse-dot" />}
          </span>
          <button
            className="dash-view-all"
            onClick={() => navigate('/warranty?status=expiring_soon')}
          >
            View All <ArrowRight size={11} />
          </button>
        </div>

        <div className="dash-warranty-list">
          {visible.map(w => {
            const tone = daysRemainingTone(w.days_remaining)
            const expired = w.days_remaining <= 0
            const critical = !expired && w.days_remaining < 7
            return (
              <div
                key={w.warranty_id}
                className={`dash-warranty-row${critical ? ' dash-warranty-row-critical' : ''}`}
              >
                <div className="dash-warranty-row-left">
                  <div className="dash-warranty-row-title">
                    <button
                      className="dash-mono dash-warranty-serial"
                      onClick={() =>
                        w.serial_number && navigate(`/machines/${w.serial_number}`)
                      }
                      disabled={!w.serial_number}
                    >
                      {w.serial_number || w.machine_id.slice(0, 8)}
                    </button>
                    {w.machine_type && (
                      <span className={`dash-warranty-type-badge dash-warranty-type-${w.machine_type.toLowerCase()}`}>
                        {w.machine_type}
                      </span>
                    )}
                  </div>
                  <div
                    className={
                      w.customer_name
                        ? 'dash-warranty-customer'
                        : 'dash-warranty-customer dash-warranty-customer-empty'
                    }
                  >
                    {w.customer_name || 'No customer set'}
                  </div>
                </div>

                <div className="dash-warranty-row-right">
                  {expired ? (
                    <div className="dash-warranty-days dash-warranty-days-expired">
                      EXPIRED
                    </div>
                  ) : (
                    <div className={`dash-warranty-days dash-warranty-days-${tone}${critical ? ' dash-warranty-days-pulse' : ''}`}>
                      {w.days_remaining}
                    </div>
                  )}
                  <div className="dash-warranty-days-label">
                    {expired ? '' : 'days left'}
                  </div>
                  <div className="dash-warranty-end-date">
                    {new Date(w.end_date + 'T00:00:00').toLocaleDateString('en-US', {
                      month: 'short', day: 'numeric', year: 'numeric',
                    })}
                  </div>

                  {isAdmin && (
                    <div className="dash-warranty-actions">
                      <button
                        className="dash-warranty-btn dash-warranty-btn-primary"
                        onClick={() => setExtendTarget({
                          warrantyId: w.warranty_id,
                          serialNumber: w.serial_number || w.machine_id,
                          currentEndDate: w.end_date,
                          currentDuration: w.duration_months,
                          daysRemaining: w.days_remaining,
                        })}
                      >
                        Extend
                      </button>
                      <button
                        className="dash-warranty-btn dash-warranty-btn-success"
                        onClick={() => handleDownload(w)}
                        disabled={downloadingId === w.warranty_id}
                      >
                        <Download size={11} />
                        {downloadingId === w.warranty_id ? '…' : 'Cert'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {remaining > 0 && (
          <div className="dash-warranty-more">
            <button
              className="dash-view-all"
              onClick={() => navigate('/warranty?status=expiring_soon')}
            >
              and {remaining} more <ArrowRight size={11} />
            </button>
          </div>
        )}
      </section>

      {extendTarget && (
        <ExtendWarrantyModal
          isOpen
          onClose={() => setExtendTarget(null)}
          warrantyId={extendTarget.warrantyId}
          serialNumber={extendTarget.serialNumber}
          currentEndDate={extendTarget.currentEndDate}
          currentDuration={extendTarget.currentDuration}
          daysRemaining={extendTarget.daysRemaining}
          onSuccess={() => {
            showToast('ok', 'Warranty extended')
            onRefresh()
          }}
        />
      )}
    </>
  )
}

// ─── Expired warranties section (collapsible, only renders when count > 0) ─

function ExpiredWarrantiesSection({
  items,
  count,
  navigate,
}: {
  items: ExpiredWarrantyEntry[]
  count: number
  navigate: ReturnType<typeof useNavigate>
}) {
  const [expanded, setExpanded] = useState(false)
  if (count === 0 || items.length === 0) return null

  const visible = items.slice(0, 10)

  return (
    <section className="dash-warranty-expired">
      <button
        className="dash-warranty-expired-head"
        onClick={() => setExpanded(e => !e)}
      >
        <span className="dash-warranty-expired-title">
          <span className="dash-warranty-expired-dot" />
          {count} Expired {count === 1 ? 'Warranty' : 'Warranties'}
        </span>
        {expanded ? <ChevronDown size={14} /> : <ChevronRightIcon size={14} />}
      </button>

      {expanded && (
        <>
          <ul className="dash-warranty-expired-list">
            {visible.map(w => (
              <li key={w.warranty_id} className="dash-warranty-expired-row">
                <button
                  className="dash-mono dash-warranty-serial"
                  onClick={() =>
                    w.serial_number && navigate(`/machines/${w.serial_number}`)
                  }
                  disabled={!w.serial_number}
                >
                  {w.serial_number || w.machine_id.slice(0, 8)}
                </button>
                <span className="dash-warranty-expired-customer">
                  {w.customer_name || '—'}
                </span>
                <span className="dash-warranty-expired-days">
                  Expired {w.days_overdue} {w.days_overdue === 1 ? 'day' : 'days'} ago
                </span>
              </li>
            ))}
          </ul>
          <div className="dash-alert-foot">
            <button
              className="dash-view-all"
              onClick={() => navigate('/warranty?status=expired')}
            >
              View All <ArrowRight size={11} />
            </button>
          </div>
        </>
      )}
    </section>
  )
}

function LowStockAlert({
  items,
  count,
  totalTracked,
  navigate,
}: {
  items: LowStockItem[]
  count: number
  totalTracked: number
  navigate: ReturnType<typeof useNavigate>
}) {
  // Empty state — small green "all stocked" card.
  if (count === 0 || items.length === 0) {
    return (
      <section className="dash-lowstock-ok">
        <PackageCheck size={20} color="#10B981" />
        <div className="dash-lowstock-ok-body">
          <div className="dash-lowstock-ok-title">
            All consumables are well stocked
          </div>
          <div className="dash-lowstock-ok-sub">
            {totalTracked} {totalTracked === 1 ? 'product' : 'products'} tracked
          </div>
        </div>
      </section>
    )
  }

  const visible = items.slice(0, 5)
  const remaining = Math.max(0, count - visible.length)
  const hasOutOfStock = items.some(i => i.quantity === 0)

  return (
    <section className="dash-lowstock-alert">
      <div className="dash-lowstock-head">
        <span className="dash-lowstock-title">
          <AlertTriangle size={14} color="#EF4444" />
          {count} {count === 1 ? 'Item' : 'Items'} Below Minimum Stock
          {hasOutOfStock && <span className="dash-pulse-dot" />}
        </span>
        <button
          className="dash-view-all"
          onClick={() => navigate('/inventory?tab=filters&alert=low_stock')}
        >
          Manage Stock <ArrowRight size={11} />
        </button>
      </div>

      <div className="dash-lowstock-list">
        {visible.map(item => {
          const tab = isFilterProduct(item.product_name) ? 'filters' : 'consumables'
          const ratio = item.min_threshold > 0
            ? item.quantity / item.min_threshold
            : 0
          const fillPct = Math.max(0, Math.min(100, ratio * 100))
          const fillColor = ratio < 0.25
            ? '#EF4444'
            : ratio < 0.75 ? '#F59E0B' : '#10B981'
          const deficit = item.min_threshold - item.quantity
          const isOut = item.quantity === 0
          return (
            <button
              key={item.product_id}
              type="button"
              className="dash-lowstock-row"
              onClick={() => navigate(`/inventory?tab=${tab}&alert=low_stock`)}
            >
              <div className="dash-lowstock-row-left">
                <div className="dash-lowstock-product">
                  {item.product_name}
                  {isOut && (
                    <span className="dash-lowstock-out-badge">OUT OF STOCK</span>
                  )}
                </div>
                <div className="dash-mono dash-lowstock-sku">
                  {item.sku || '—'}
                </div>
              </div>

              <div className="dash-lowstock-row-center">
                <div className="dash-mono dash-lowstock-qty">{item.quantity}</div>
                <div className="dash-lowstock-qty-label">in stock</div>
              </div>

              <div className="dash-lowstock-row-right">
                <div className="dash-lowstock-min">Min: {item.min_threshold}</div>
                <div className="dash-lowstock-deficit">-{deficit} below</div>
                <div className="dash-lowstock-bar">
                  <div
                    className="dash-lowstock-bar-fill"
                    style={{ width: `${fillPct}%`, background: fillColor }}
                  />
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {remaining > 0 && (
        <div className="dash-lowstock-more">
          <button
            className="dash-view-all"
            onClick={() => navigate('/inventory?tab=filters&alert=low_stock')}
          >
            and {remaining} more <ArrowRight size={11} />
          </button>
        </div>
      )}
    </section>
  )
}

const FIVE_MINUTES_MS = 5 * 60 * 1000

function RecentActivitySection({
  items,
  navigate,
}: {
  items: RecentActivityEntry[]
  navigate: ReturnType<typeof useNavigate>
}) {
  // Cap the dashboard timeline at 10 entries; the /activity page shows more.
  const visible = items.slice(0, 10)
  const now = Date.now()

  return (
    <section className="dash-section dash-activity-section">
      <div className="dash-section-head">
        <span className="dash-section-title">
          <Activity size={13} color="#64748B" /> RECENT ACTIVITY
        </span>
        <button
          className="dash-view-all"
          onClick={() => navigate('/activity')}
        >
          View All <ArrowRight size={11} />
        </button>
      </div>

      {visible.length === 0 ? (
        <div className="dash-activity-empty">
          <Clock size={16} color="#475569" />
          <span>No machine status changes yet</span>
        </div>
      ) : (
        <ul className="dash-activity-timeline">
          {visible.map((a, idx) => {
            const dotColor = statusDotColor(a.to_status)
            const machineType = machineTypeFromSerial(a.serial_number)
            const isFresh =
              now - new Date(a.created_at).getTime() < FIVE_MINUTES_MS
            const fullTimestamp = formatFullDateTime(a.created_at)
            return (
              <li
                key={a.id}
                className={`dash-activity-entry${isFresh ? ' dash-activity-entry-fresh' : ''}`}
                style={{ animationDelay: `${idx * 50}ms` }}
              >
                <span
                  className="dash-activity-dot"
                  style={{
                    background: dotColor,
                    boxShadow: `0 0 0 3px rgba(15, 23, 42, 1), 0 0 0 4px ${dotColor}33`,
                  }}
                />
                <div className="dash-activity-content">
                  <div className="dash-activity-headline">
                    <button
                      type="button"
                      className="dash-mono dash-activity-serial"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (a.serial_number) navigate(`/machines/${a.serial_number}`)
                      }}
                      disabled={!a.serial_number}
                    >
                      {a.serial_number || a.machine_id.slice(0, 8)}
                    </button>
                    {machineType && (
                      <span
                        className={`dash-activity-type dash-activity-type-${machineType.toLowerCase()}`}
                      >
                        {machineType}
                      </span>
                    )}
                    {a.from_status && (
                      <>
                        <span
                          className={`dash-activity-status-badge dash-activity-status-${a.from_status}`}
                        >
                          {a.from_status}
                        </span>
                        <span className="dash-activity-arrow">→</span>
                      </>
                    )}
                    <span
                      className={`dash-activity-status-badge dash-activity-status-${a.to_status}`}
                    >
                      {a.to_status}
                    </span>
                  </div>
                  {a.changed_by_name && (
                    <div className="dash-activity-by">
                      by {a.changed_by_name}
                    </div>
                  )}
                  {a.reason && (
                    <div className="dash-activity-reason">
                      {truncate(a.reason, 60)}
                    </div>
                  )}
                  <div
                    className="dash-activity-time"
                    title={fullTimestamp}
                  >
                    {formatRelative(a.created_at)}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/** Compare-fn: urgent first, then high/medium/low; newer-first within tie. */
function compareByPriority(a: RecentIssueEntry, b: RecentIssueEntry): number {
  const rank = (p: string): number => {
    switch (p) {
      case 'urgent': return 0
      case 'high':   return 1
      case 'medium': return 2
      case 'low':    return 3
      default:       return 99
    }
  }
  const diff = rank(a.priority) - rank(b.priority)
  if (diff !== 0) return diff
  return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
}

function priorityBorderColor(priority: string): string {
  switch (priority) {
    case 'urgent': return '#EF4444'
    case 'high':   return '#F59E0B'
    case 'medium': return '#3B82F6'
    case 'low':    return '#64748B'
    default:       return '#64748B'
  }
}

function IssueTrackerWidget({
  items,
  counts,
  isAdmin,
  navigate,
  onRefresh,
  showToast,
}: {
  items: RecentIssueEntry[]
  counts: IssueCounts | undefined
  isAdmin: boolean
  navigate: ReturnType<typeof useNavigate>
  onRefresh: () => void
  showToast: (kind: 'ok' | 'err', msg: string) => void
}) {
  const [resolveTarget, setResolveTarget] = useState<RecentIssueEntry | null>(null)
  const [startingId, setStartingId] = useState<string | null>(null)

  const open = counts?.open ?? 0
  const inProgress = counts?.in_progress ?? 0
  const urgent = counts?.urgent ?? 0
  const high = counts?.high ?? 0
  const resolved = counts?.resolved ?? 0
  const activeTotal = open + inProgress

  // Empty state — green "all clear" card.
  if (activeTotal === 0 || items.length === 0) {
    return (
      <section className="dash-issue-ok">
        <CheckCircle size={20} color="#10B981" />
        <div className="dash-issue-ok-body">
          <div className="dash-issue-ok-title">No open issues</div>
          <div className="dash-issue-ok-sub">
            {resolved} resolved all time
          </div>
        </div>
      </section>
    )
  }

  const sorted = [...items].sort(compareByPriority)
  const visible = sorted.slice(0, 5)
  const remaining = Math.max(0, activeTotal - visible.length)
  const hasUrgent = items.some(i => i.priority === 'urgent')

  // Quick-start: PUT status=in_progress with no resolution_notes required.
  const handleStart = async (issue: RecentIssueEntry) => {
    setStartingId(issue.id)
    try {
      await apiPut(`/api/issues/${issue.id}/status`, { status: 'in_progress' })
      showToast('ok', 'Issue marked in progress')
      onRefresh()
    } catch (e) {
      showToast('err', (e as Error).message || 'Failed to start')
    } finally {
      setStartingId(null)
    }
  }

  // Use the appropriate count-badge color depending on severity mix.
  const headBadgeColor = urgent > 0 ? '#EF4444' : '#3B82F6'

  return (
    <>
      <section className="dash-section dash-issues-section">
        <div className="dash-section-head">
          <span className="dash-section-title">
            <ListChecks size={13} color="#EF4444" /> OPEN ISSUES
            <span
              className="dash-issues-count-badge"
              style={{ background: headBadgeColor }}
            >
              {activeTotal}
            </span>
            {hasUrgent && <span className="dash-pulse-dot" />}
          </span>
          <button
            className="dash-view-all"
            onClick={() => navigate('/issues?status=open')}
          >
            View All <ArrowRight size={11} />
          </button>
        </div>

        {/* Mini summary bar */}
        <div className="dash-issues-minibar">
          {open > 0 && (
            <span className="dash-issues-seg dash-issues-seg-open">
              {open} Open
            </span>
          )}
          {inProgress > 0 && (
            <span className="dash-issues-seg dash-issues-seg-progress">
              {inProgress} In Progress
            </span>
          )}
          {urgent > 0 && (
            <span className="dash-issues-seg dash-issues-seg-urgent">
              <span className="dash-issues-seg-dot" /> {urgent} Urgent
            </span>
          )}
          {high > 0 && (
            <span className="dash-issues-seg dash-issues-seg-high">
              <span className="dash-issues-seg-dot" /> {high} High
            </span>
          )}
        </div>

        {/* Cards */}
        <ul className="dash-issues-list">
          {visible.map(issue => {
            const borderColor = priorityBorderColor(issue.priority)
            const serial = issue.machine_serial || issue.serial_number
            const isUrgent = issue.priority === 'urgent'
            const machineType = issue.machine_type
            return (
              <li
                key={issue.id}
                className={`dash-issue-card${isUrgent ? ' dash-issue-card-urgent' : ''}`}
                style={{ borderLeft: `3px solid ${borderColor}` }}
              >
                <div className="dash-issue-row1">
                  <span
                    className={`dash-issue-prio-badge dash-issue-prio-${issue.priority}`}
                  >
                    {issue.priority}
                  </span>
                  <button
                    type="button"
                    className="dash-issue-card-title"
                    onClick={() => navigate('/issues?status=open')}
                  >
                    {issue.title}
                  </button>
                </div>

                <div className="dash-issue-row2">
                  {serial ? (
                    <button
                      type="button"
                      className="dash-mono dash-issue-serial-link"
                      onClick={() => navigate(`/machines/${serial}`)}
                    >
                      {serial}
                    </button>
                  ) : (
                    <span className="dash-mono dash-issue-serial">
                      {issue.machine_id.slice(0, 8)}
                    </span>
                  )}
                  {machineType && (
                    <span
                      className={`dash-issue-type dash-issue-type-${machineType.toLowerCase()}`}
                    >
                      {machineType}
                    </span>
                  )}
                  <span
                    className={`dash-issue-status-badge dash-issue-status-${issue.status}`}
                  >
                    {issue.status.replace('_', ' ')}
                  </span>
                </div>

                <div className="dash-issue-row3">
                  <span className="dash-issue-byline">
                    {issue.reported_by_name
                      ? `Reported by ${issue.reported_by_name}`
                      : 'Reported'}
                    {' · '}
                    {formatRelative(issue.created_at)}
                  </span>
                  {isAdmin && (
                    <div className="dash-issue-actions">
                      {issue.status === 'open' && (
                        <button
                          type="button"
                          className="dash-issue-btn dash-issue-btn-start"
                          onClick={() => handleStart(issue)}
                          disabled={startingId === issue.id}
                        >
                          {startingId === issue.id ? '…' : 'Start'}
                        </button>
                      )}
                      {issue.status === 'in_progress' && (
                        <button
                          type="button"
                          className="dash-issue-btn dash-issue-btn-resolve"
                          onClick={() => setResolveTarget(issue)}
                        >
                          Resolve
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ul>

        {remaining > 0 && (
          <div className="dash-issues-more">
            <button
              className="dash-view-all"
              onClick={() => navigate('/issues?status=open')}
            >
              and {remaining} more <ArrowRight size={11} />
            </button>
          </div>
        )}
      </section>

      {resolveTarget && (
        <ResolveIssueModal
          issue={resolveTarget}
          onClose={() => setResolveTarget(null)}
          onSuccess={() => {
            showToast('ok', 'Issue resolved')
            setResolveTarget(null)
            onRefresh()
          }}
          onError={(msg) => showToast('err', msg)}
        />
      )}
    </>
  )
}

function ResolveIssueModal({
  issue,
  onClose,
  onSuccess,
  onError,
}: {
  issue: RecentIssueEntry
  onClose: () => void
  onSuccess: () => void
  onError: (msg: string) => void
}) {
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const trimmed = notes.trim()

  const submit = async () => {
    if (!trimmed) {
      onError('Resolution notes are required')
      return
    }
    setSubmitting(true)
    try {
      await apiPut(`/api/issues/${issue.id}/status`, {
        status: 'resolved',
        resolution_notes: trimmed,
      })
      onSuccess()
    } catch (e) {
      onError((e as Error).message || 'Failed to resolve')
      setSubmitting(false)
    }
  }

  return (
    <div className="dash-modal-backdrop" onClick={onClose}>
      <div
        className="dash-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dash-modal-head">
          <span className="dash-modal-title">Resolve issue</span>
          <button
            type="button"
            className="dash-modal-close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div className="dash-modal-body">
          <div className="dash-modal-subject">{issue.title}</div>
          <label className="dash-modal-label">
            Resolution notes <span className="dash-modal-req">*</span>
          </label>
          <textarea
            className="dash-modal-textarea"
            rows={4}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="What was done to resolve this issue?"
            autoFocus
          />
        </div>
        <div className="dash-modal-foot">
          <button
            type="button"
            className="dash-issue-btn"
            onClick={onClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="dash-issue-btn dash-issue-btn-resolve"
            onClick={submit}
            disabled={submitting || !trimmed}
          >
            {submitting ? 'Resolving…' : 'Resolve'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Card / shared components ─────────────────────────────────────────────

function SummaryCard({
  loading,
  icon,
  label,
  count,
  color,
  subtitle,
  onClick,
}: {
  loading: boolean
  icon: React.ReactNode
  label: string
  count: number
  color: string
  subtitle: React.ReactNode
  onClick: () => void
}) {
  return (
    <button className="dash-card dash-card-button" onClick={onClick}>
      <div className="dash-card-head">
        <span className="dash-card-label">{label}</span>
        {icon}
      </div>
      {loading ? (
        <div className="dash-card-skel" />
      ) : (
        <div className="dash-card-count" style={{ color }}>{count}</div>
      )}
      <div className="dash-card-sub">{subtitle}</div>
    </button>
  )
}

interface ActionItem {
  label: string
  icon: React.ReactNode
  to: string
}

function QuickActions({
  actions,
  navigate,
  wide,
}: {
  actions: ActionItem[]
  navigate: ReturnType<typeof useNavigate>
  wide?: boolean
}) {
  return (
    <section className="dash-section">
      <div className="dash-section-head">
        <span className="dash-section-title">
          <Zap size={13} color="#3B82F6" /> QUICK ACTIONS
        </span>
      </div>
      <div className={`dash-actions-grid${wide ? ' dash-actions-grid-wide' : ''}`}>
        {actions.map(a => (
          <button
            key={a.label}
            className="dash-action"
            onClick={() => navigate(a.to)}
          >
            <span className="dash-action-icon">{a.icon}</span>
            <span className="dash-action-label">{a.label}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
