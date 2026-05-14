/**
 * Sprint 4 Task 4.5 — Notification bell.
 *
 * Header-mounted bell with:
 *  - 30-second poll of GET /api/notifications/unread-count (count only)
 *  - Click → dropdown that lazy-loads GET /api/notifications?limit=10
 *  - Click an item → mark read + navigate by entity_type
 *  - Footer actions: Mark all read, Clear read
 *  - Outside-click closes the dropdown
 *  - `onUnreadCountChange` lifts the count up to Layout for the sidebar badge
 *
 * The poll only fetches the count; the full list is fetched on dropdown open
 * and again after destructive actions (mark/clear/read).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
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
} from 'lucide-react'
import { apiGet, apiPut, apiDelete } from '../lib/api'

const POLL_INTERVAL_MS = 30_000
const DROPDOWN_LIMIT = 10

export interface NotificationItem {
  id: string
  user_id: string
  title: string
  message: string
  type: string
  entity_type: string | null
  entity_id: string | null
  is_read: boolean
  created_at: string
}

interface Props {
  /** Called whenever the bell's known unread count changes. */
  onUnreadCountChange?: (count: number) => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────

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

/** Map a notification type → { Icon, bg color, fg color }. */
function iconForType(type: string): {
  Icon: typeof Bell
  bg: string
  fg: string
} {
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

/** Map (entity_type, entity_id) → route, or null to stay on the same page. */
function navTargetFor(n: NotificationItem): string | null {
  if (!n.entity_type) return null
  switch (n.entity_type) {
    case 'machine':
      return n.entity_id ? `/machines/${n.entity_id}` : '/inventory?tab=machines'
    case 'warranty':
      return '/warranty'
    case 'reservation':
      return '/inventory?tab=reservations'
    case 'machine_issue':
      return '/issues'
    default:
      return null
  }
}

// ─── Component ────────────────────────────────────────────────────────────

export default function NotificationBell({ onUnreadCountChange }: Props) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const [items, setItems] = useState<NotificationItem[]>([])
  const [loadingList, setLoadingList] = useState(false)
  const [pulse, setPulse] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const lastKnownCount = useRef(0)
  // Latest callback so the polling effect doesn't restart on rerender.
  const onCountChangeRef = useRef(onUnreadCountChange)
  useEffect(() => { onCountChangeRef.current = onUnreadCountChange }, [onUnreadCountChange])

  // Broadcast count up + run the badge pulse if it increased.
  const setCount = useCallback((next: number) => {
    setUnreadCount(prev => {
      if (next > prev) {
        setPulse(true)
        // Reset pulse after the animation finishes.
        window.setTimeout(() => setPulse(false), 1500)
      }
      return next
    })
    lastKnownCount.current = next
    onCountChangeRef.current?.(next)
  }, [])

  // Fetch unread count (poll-cheap, count only).
  const fetchCount = useCallback(async () => {
    try {
      const data = await apiGet<{ count: number }>(
        '/api/notifications/unread-count',
      )
      setCount(data.count ?? 0)
    } catch {
      // Best-effort — keep the previous count rather than zeroing it out.
    }
  }, [setCount])

  // Fetch the dropdown list (only when opened or after a mutation).
  const fetchList = useCallback(async () => {
    setLoadingList(true)
    try {
      const data = await apiGet<NotificationItem[]>(
        `/api/notifications?limit=${DROPDOWN_LIMIT}`,
      )
      setItems(Array.isArray(data) ? data : [])
    } catch {
      setItems([])
    } finally {
      setLoadingList(false)
    }
  }, [])

  // Initial fetch + 30s poll of the count.
  useEffect(() => {
    fetchCount()
    const interval = window.setInterval(fetchCount, POLL_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [fetchCount])

  // When the dropdown opens, fetch the list.
  useEffect(() => {
    if (open) fetchList()
  }, [open, fetchList])

  // Close on outside click.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const handleItemClick = async (n: NotificationItem) => {
    // Best-effort mark-as-read; update the local list immediately for
    // perceived responsiveness, refresh the count from the server right after.
    if (!n.is_read) {
      setItems(prev => prev.map(it => it.id === n.id ? { ...it, is_read: true } : it))
      try {
        await apiPut(`/api/notifications/${n.id}/read`, {})
      } catch {
        // Ignore — the next poll will reconcile.
      }
      fetchCount()
    }
    const target = navTargetFor(n)
    setOpen(false)
    if (target) navigate(target)
  }

  const handleMarkAllRead = async () => {
    try {
      await apiPut('/api/notifications/read-all', {})
      setItems(prev => prev.map(it => ({ ...it, is_read: true })))
      setCount(0)
    } catch {
      /* surface nothing — quiet failure for a header action */
    }
  }

  const handleClearRead = async () => {
    try {
      await apiDelete('/api/notifications/clear-read')
      // Drop locally-read items; fetch fresh list for accuracy.
      await fetchList()
      fetchCount()
    } catch {
      /* ignore */
    }
  }

  const handleViewAll = () => {
    setOpen(false)
    navigate('/notifications')
  }

  const badgeText = unreadCount > 9 ? '9+' : String(unreadCount)

  return (
    <div className="notif-wrapper" ref={wrapperRef}>
      <button
        className={`notif-bell-btn${unreadCount > 0 ? ' notif-bell-has-unread' : ''}`}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        onClick={() => setOpen(o => !o)}
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span
            className={`notif-badge${pulse ? ' notif-badge-pulse' : ''}${
              unreadCount > 9 ? ' notif-badge-wide' : ''
            }`}
          >
            {badgeText}
          </span>
        )}
      </button>

      {open && (
        <div className="notif-dropdown" role="dialog" aria-label="Notifications">
          <div className="notif-dropdown-head">
            <span className="notif-dropdown-title">
              Notifications
              {unreadCount > 0 && (
                <span className="notif-dropdown-count">{unreadCount}</span>
              )}
            </span>
            {unreadCount > 0 && (
              <button
                type="button"
                className="notif-dropdown-action"
                onClick={handleMarkAllRead}
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="notif-dropdown-list">
            {loadingList && items.length === 0 ? (
              <div className="notif-dropdown-loading">Loading…</div>
            ) : items.length === 0 ? (
              <div className="notif-dropdown-empty">
                <Bell size={32} color="#334155" />
                <div className="notif-empty-title">No notifications yet</div>
                <div className="notif-empty-sub">
                  You'll see alerts for warranties, stock, and reservations here
                </div>
              </div>
            ) : (
              items.map(n => {
                const { Icon, bg, fg } = iconForType(n.type)
                return (
                  <button
                    type="button"
                    key={n.id}
                    className={`notif-item${n.is_read ? '' : ' notif-item-unread'}`}
                    style={n.is_read ? undefined : { borderLeftColor: fg }}
                    onClick={() => handleItemClick(n)}
                  >
                    <span
                      className="notif-item-icon"
                      style={{ background: bg, color: fg }}
                    >
                      <Icon size={16} />
                    </span>
                    <div className="notif-item-body">
                      <div className="notif-item-title">{n.title}</div>
                      <div className="notif-item-message">{n.message}</div>
                      <div className="notif-item-time">
                        {formatRelative(n.created_at)}
                      </div>
                    </div>
                  </button>
                )
              })
            )}
          </div>

          <div className="notif-dropdown-foot">
            <button
              type="button"
              className="notif-foot-primary"
              onClick={handleViewAll}
            >
              View All Notifications
            </button>
            <button
              type="button"
              className="notif-foot-secondary"
              onClick={handleClearRead}
            >
              Clear read
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
