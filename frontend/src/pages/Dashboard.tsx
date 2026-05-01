import { useEffect, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Package,
  Shield,
  AlertTriangle,
  Clock,
  Plus,
  CalendarCheck,
  Beaker,
  Zap,
  ListChecks,
  Eye,
  ArrowRight,
} from 'lucide-react'
import { useAuth } from '../lib/auth'
import { apiGet } from '../lib/api'
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
  customer_name: string | null
  end_date: string
  days_remaining: number
}

interface RecentIssueEntry {
  id: string
  machine_id: string
  serial_number: string | null
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
  low_stock: { count: number; items: LowStockItem[] }
  recent_activity: RecentActivityEntry[]
  recent_issues: RecentIssueEntry[]
  expiring_warranties: ExpiringWarrantyEntry[]
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
    case 'ordered':   return '#3B82F6'
    case 'sold':      return '#A855F7'
    case 'delivered': return '#14B8A6'
    case 'returned':  return '#94A3B8'
    default:          return '#64748B'
  }
}

function priorityClass(p: string): string {
  return `dash-issue-prio-${p}`
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

  const [data, setData] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

      {isRep
        ? <RepView data={data} loading={loading} navigate={navigate} />
        : <AdminView data={data} loading={loading} navigate={navigate} />
      }
    </div>
  )
}

// ─── ADMIN VIEW ───────────────────────────────────────────────────────────

function AdminView({
  data,
  loading,
  navigate,
}: {
  data: DashboardSummary | null
  loading: boolean
  navigate: ReturnType<typeof useNavigate>
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
            navigate={navigate}
          />
          <LowStockAlert
            items={data?.low_stock?.items ?? []}
            navigate={navigate}
          />
          <RecentActivitySection
            items={data?.recent_activity ?? []}
            navigate={navigate}
          />
        </div>
        <div className="dash-col-right">
          <OpenIssuesSection
            items={data?.recent_issues ?? []}
            count={issuesActive}
            navigate={navigate}
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

function WarrantyExpiringAlert({
  items,
  count,
  navigate,
}: {
  items: ExpiringWarrantyEntry[]
  count: number
  navigate: ReturnType<typeof useNavigate>
}) {
  if (count === 0 || items.length === 0) return null
  return (
    <section className="dash-alert dash-alert-warn">
      <div className="dash-alert-head">
        <span className="dash-alert-title">
          <AlertTriangle size={14} color="#F59E0B" />
          {count} {count === 1 ? 'warranty' : 'warranties'} expiring within 30 days
        </span>
      </div>
      <ul className="dash-alert-list">
        {items.slice(0, 5).map(w => (
          <li key={w.warranty_id} className="dash-alert-row">
            <button
              className="dash-link dash-mono"
              onClick={() => w.serial_number && navigate(`/machines/${w.serial_number}`)}
              disabled={!w.serial_number}
            >
              {w.serial_number || w.machine_id.slice(0, 8)}
            </button>
            <span className="dash-alert-customer">{w.customer_name || '—'}</span>
            <span className="dash-warn-num">{w.days_remaining}d left</span>
          </li>
        ))}
      </ul>
      <div className="dash-alert-foot">
        <button
          className="dash-view-all"
          onClick={() => navigate('/warranty?status=expiring_soon')}
        >
          View All <ArrowRight size={11} />
        </button>
      </div>
    </section>
  )
}

function LowStockAlert({
  items,
  navigate,
}: {
  items: LowStockItem[]
  navigate: ReturnType<typeof useNavigate>
}) {
  if (items.length === 0) return null
  return (
    <section className="dash-alert dash-alert-danger">
      <div className="dash-alert-head">
        <span className="dash-alert-title">
          <AlertTriangle size={14} color="#EF4444" />
          {items.length} {items.length === 1 ? 'item' : 'items'} below minimum stock
        </span>
      </div>
      <ul className="dash-alert-list">
        {items.slice(0, 5).map(item => {
          const tab = isFilterProduct(item.product_name) ? 'filters' : 'consumables'
          return (
            <li key={item.product_id} className="dash-alert-row">
              <button
                className="dash-link dash-alert-product"
                onClick={() => navigate(`/inventory?tab=${tab}&alert=low_stock`)}
              >
                {item.product_name}
              </button>
              <span className="dash-mono dash-alert-sku">{item.sku || '—'}</span>
              <span className="dash-alert-counts">
                <span className="dash-danger-num">Current: {item.quantity}</span>
                <span className="dash-alert-threshold">Min: {item.min_threshold}</span>
              </span>
            </li>
          )
        })}
      </ul>
      <div className="dash-alert-foot">
        <button
          className="dash-view-all"
          onClick={() => navigate('/inventory?tab=consumables&alert=low_stock')}
        >
          View All <ArrowRight size={11} />
        </button>
      </div>
    </section>
  )
}

function RecentActivitySection({
  items,
  navigate,
}: {
  items: RecentActivityEntry[]
  navigate: ReturnType<typeof useNavigate>
}) {
  return (
    <section className="dash-section">
      <div className="dash-section-head">
        <span className="dash-section-title">
          <Clock size={13} color="#64748B" /> RECENT ACTIVITY
        </span>
      </div>
      {items.length === 0 ? (
        <div className="dash-empty">No recent activity yet</div>
      ) : (
        <ul className="dash-activity-list">
          {items.map(a => (
            <li
              key={a.id}
              className="dash-activity-row"
              onClick={() => a.serial_number && navigate(`/machines/${a.serial_number}`)}
            >
              <span
                className="dash-activity-dot"
                style={{ background: statusDotColor(a.to_status) }}
              />
              <div className="dash-activity-body">
                <div className="dash-activity-line">
                  <span className="dash-mono">{a.serial_number || a.machine_id.slice(0, 8)}</span>
                  <span className="dash-activity-arrow">→</span>
                  <span className="dash-activity-status">{a.to_status}</span>
                  {a.changed_by_name && (
                    <span className="dash-activity-by">by {a.changed_by_name}</span>
                  )}
                </div>
                {a.reason && (
                  <div className="dash-activity-reason">
                    {truncate(a.reason, 50)}
                  </div>
                )}
              </div>
              <span className="dash-activity-time">{formatRelative(a.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="dash-alert-foot">
        <button
          className="dash-view-all"
          onClick={() => navigate('/inventory?tab=machines')}
        >
          View All <ArrowRight size={11} />
        </button>
      </div>
    </section>
  )
}

function OpenIssuesSection({
  items,
  count,
  navigate,
}: {
  items: RecentIssueEntry[]
  count: number
  navigate: ReturnType<typeof useNavigate>
}) {
  return (
    <section className="dash-section">
      <div className="dash-section-head">
        <span className="dash-section-title">
          <ListChecks size={13} color="#EF4444" /> OPEN ISSUES
          {count > 0 && <span className="dash-section-count">{count}</span>}
        </span>
      </div>
      {items.length === 0 ? (
        <div className="dash-empty">No open issues</div>
      ) : (
        <ul className="dash-issue-list">
          {items.map(it => (
            <li
              key={it.id}
              className={`dash-issue-row ${priorityClass(it.priority)}`}
              onClick={() => navigate('/issues')}
            >
              <div className="dash-issue-title">{it.title}</div>
              <div className="dash-issue-meta">
                {it.serial_number ? (
                  <button
                    type="button"
                    className="dash-mono dash-issue-serial-link"
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/machines/${it.serial_number}`)
                    }}
                  >
                    {it.serial_number}
                  </button>
                ) : (
                  <span className="dash-mono dash-issue-serial">
                    {it.machine_id.slice(0, 8)}
                  </span>
                )}
                <span className={`dash-issue-status dash-issue-status-${it.status}`}>
                  {it.status.replace('_', ' ')}
                </span>
                {it.reported_by_name && (
                  <span className="dash-issue-by">by {it.reported_by_name}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="dash-alert-foot">
        <button
          className="dash-view-all"
          onClick={() => navigate('/issues')}
        >
          View All <ArrowRight size={11} />
        </button>
      </div>
    </section>
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
