/**
 * Sprint 4 Task 4.5 — Full notifications page.
 *
 * Filter tabs (All / Unread / Warranty / Stock / Reservations / Issues),
 * per-card delete, bulk Mark-all-read and Clear-read, "Load more" pagination
 * (20 at a time). Reuses the icon/route helpers from NotificationBell via
 * locally-duplicated minimal copies — the bell file isn't a great public API
 * yet so we keep this page self-contained.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell,
  Shield,
  Package,
  RefreshCw,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Trash2,
  Filter,
} from 'lucide-react'
import { apiGet, apiPut, apiDelete } from '../lib/api'
import type { NotificationItem } from '../components/NotificationBell'
import './Notifications.css'

const PAGE_SIZE = 20

type FilterKey =
  | 'all'
  | 'unread'
  | 'warranty'
  | 'stock'
  | 'reservations'
  | 'issues'

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: 'all',          label: 'All' },
  { key: 'unread',       label: 'Unread' },
  { key: 'warranty',     label: 'Warranty' },
  { key: 'stock',        label: 'Stock' },
  { key: 'reservations', label: 'Reservations' },
  { key: 'issues',       label: 'Issues' },
]

/** Decide if a notification belongs in a given filter bucket. */
function matchesFilter(n: NotificationItem, key: FilterKey): boolean {
  switch (key) {
    case 'all':          return true
    case 'unread':       return !n.is_read
    case 'warranty':     return n.type === 'warranty_expiring'
    case 'stock':        return n.type === 'low_stock'
    case 'reservations':
      return n.type.startsWith('reservation_')
    case 'issues':
      return n.type === 'ticket_update' || n.entity_type === 'machine_issue'
  }
}

function formatRelative(value: string): string {
  const then = new Date(value).getTime()
  const diff = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`
  return new Date(value).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })
}

function iconForType(type: string) {
  switch (type) {
    case 'warranty_expiring':
      return { Icon: Shield,        bg: 'rgba(245, 158, 11, 0.15)', fg: '#F59E0B' }
    case 'low_stock':
      return { Icon: Package,       bg: 'rgba(239, 68, 68, 0.15)',  fg: '#EF4444' }
    case 'machine_status_change':
      return { Icon: RefreshCw,     bg: 'rgba(59, 130, 246, 0.15)', fg: '#3B82F6' }
    case 'reservation_request':
    case 'reservation_expiring':
      return { Icon: Clock,         bg: 'rgba(245, 158, 11, 0.15)', fg: '#F59E0B' }
    case 'reservation_approved':
      return { Icon: CheckCircle,   bg: 'rgba(16, 185, 129, 0.15)', fg: '#10B981' }
    case 'reservation_denied':
      return { Icon: XCircle,       bg: 'rgba(239, 68, 68, 0.15)',  fg: '#EF4444' }
    case 'ticket_update':
    case 'order_update':
      return { Icon: AlertTriangle, bg: 'rgba(139, 92, 246, 0.15)', fg: '#A78BFA' }
    default:
      return { Icon: Bell,          bg: 'rgba(100, 116, 139, 0.15)', fg: '#94A3B8' }
  }
}

function navTargetFor(n: NotificationItem): string | null {
  if (!n.entity_type) return null
  switch (n.entity_type) {
    case 'machine':
      return n.entity_id ? `/machines/${n.entity_id}` : '/inventory?tab=machines'
    case 'warranty':       return '/warranty'
    case 'reservation':    return '/inventory?tab=reservations'
    case 'machine_issue':  return '/issues'
    default:               return null
  }
}

// ─── Component ────────────────────────────────────────────────────────────

export default function Notifications() {
  const navigate = useNavigate()
  const [items, setItems] = useState<NotificationItem[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<FilterKey>('all')
  const [visible, setVisible] = useState(PAGE_SIZE)
  const [bulkBusy, setBulkBusy] = useState(false)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      // The list endpoint paginates server-side; fetch the most recent 50 — the
      // dashboard is the firehose for older history. "Load more" extends within
      // this set; if we exceed it we re-fetch with a larger offset.
      const data = await apiGet<NotificationItem[]>(
        '/api/notifications?limit=50',
      )
      setItems(Array.isArray(data) ? data : [])
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  // Reset visible-window when filter changes.
  useEffect(() => {
    setVisible(PAGE_SIZE)
  }, [filter])

  const counts = useMemo(() => ({
    all:          items.length,
    unread:       items.filter(n => !n.is_read).length,
    warranty:     items.filter(n => matchesFilter(n, 'warranty')).length,
    stock:        items.filter(n => matchesFilter(n, 'stock')).length,
    reservations: items.filter(n => matchesFilter(n, 'reservations')).length,
    issues:       items.filter(n => matchesFilter(n, 'issues')).length,
  } as Record<FilterKey, number>), [items])

  const filtered = useMemo(
    () => items.filter(n => matchesFilter(n, filter)),
    [items, filter],
  )
  const shown = filtered.slice(0, visible)
  const hasMore = filtered.length > visible

  const handleClick = async (n: NotificationItem) => {
    if (!n.is_read) {
      setItems(prev => prev.map(it => it.id === n.id ? { ...it, is_read: true } : it))
      try {
        await apiPut(`/api/notifications/${n.id}/read`, {})
      } catch { /* ignore — local state already updated */ }
    }
    const target = navTargetFor(n)
    if (target) navigate(target)
  }

  const handleDelete = async (n: NotificationItem, e: React.MouseEvent) => {
    e.stopPropagation()
    setItems(prev => prev.filter(it => it.id !== n.id))
    try {
      await apiDelete(`/api/notifications/${n.id}`)
    } catch {
      // Refetch on failure so the UI doesn't lie about state.
      fetchAll()
    }
  }

  const handleMarkAllRead = async () => {
    setBulkBusy(true)
    try {
      await apiPut('/api/notifications/read-all', {})
      setItems(prev => prev.map(it => ({ ...it, is_read: true })))
    } catch { /* ignore */ }
    setBulkBusy(false)
  }

  const handleClearRead = async () => {
    setBulkBusy(true)
    try {
      await apiDelete('/api/notifications/clear-read')
      setItems(prev => prev.filter(it => !it.is_read))
    } catch { /* ignore */ }
    setBulkBusy(false)
  }

  return (
    <div className="notif-page">
      <div className="notif-page-head">
        <div className="notif-page-tabs" role="tablist">
          <Filter size={14} color="#64748B" />
          {FILTERS.map(f => (
            <button
              key={f.key}
              role="tab"
              aria-selected={filter === f.key}
              className={`notif-page-tab${filter === f.key ? ' notif-page-tab-active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
              <span className="notif-page-tab-count">{counts[f.key]}</span>
            </button>
          ))}
        </div>
        <div className="notif-page-actions">
          <button
            type="button"
            className="notif-page-btn"
            onClick={handleMarkAllRead}
            disabled={bulkBusy || counts.unread === 0}
          >
            Mark all read
          </button>
          <button
            type="button"
            className="notif-page-btn notif-page-btn-danger"
            onClick={handleClearRead}
            disabled={bulkBusy || (counts.all - counts.unread) === 0}
          >
            Clear all read
          </button>
        </div>
      </div>

      {loading ? (
        <div className="notif-page-loading">Loading notifications…</div>
      ) : shown.length === 0 ? (
        <div className="notif-page-empty">
          <Bell size={40} color="#334155" />
          <div className="notif-empty-title">No notifications</div>
          <div className="notif-empty-sub">
            {filter === 'all'
              ? "You'll see alerts for warranties, stock, and reservations here"
              : 'Nothing matches this filter'}
          </div>
        </div>
      ) : (
        <ul className="notif-page-list">
          {shown.map(n => {
            const { Icon, bg, fg } = iconForType(n.type)
            return (
              <li
                key={n.id}
                className={`notif-page-card${n.is_read ? '' : ' notif-page-card-unread'}`}
                style={n.is_read ? undefined : { borderLeftColor: fg }}
                onClick={() => handleClick(n)}
                role="button"
                tabIndex={0}
              >
                <span
                  className="notif-page-icon"
                  style={{ background: bg, color: fg }}
                >
                  <Icon size={18} />
                </span>
                <div className="notif-page-body">
                  <div className="notif-page-title">{n.title}</div>
                  <div className="notif-page-message">{n.message}</div>
                  <div className="notif-page-meta">
                    <span className="notif-page-type">{n.type.replace(/_/g, ' ')}</span>
                    <span>·</span>
                    <span>{formatRelative(n.created_at)}</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="notif-page-delete"
                  onClick={(e) => handleDelete(n, e)}
                  aria-label="Delete notification"
                >
                  <Trash2 size={14} />
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {hasMore && (
        <div className="notif-page-more">
          <button
            type="button"
            className="notif-page-btn"
            onClick={() => setVisible(v => v + PAGE_SIZE)}
          >
            Load more ({filtered.length - visible} remaining)
          </button>
        </div>
      )}
    </div>
  )
}
