import { useState, useRef, useEffect } from 'react'
import type { ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Target,
  Users,
  Package,
  ClipboardList,
  DollarSign,
  Headphones,
  Shield,
  UserCog,
  Settings,
  ChevronLeft,
  ChevronRight,
  Bell,
  LogOut,
  Sun,
  Moon,
  AlertTriangle,
} from 'lucide-react'
import { useAuth } from '../lib/auth'
import { useTheme } from '../context/ThemeContext'
import { apiGet } from '../lib/api'
import './Layout.css'

const ROUTE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/leads': 'Leads',
  '/customers': 'Customers',
  '/inventory': 'Inventory',
  '/orders': 'Orders',
  '/issues': 'Issues',
  '/commissions': 'Commissions',
  '/tickets': 'Tickets',
  '/warranty': 'Warranty',
  '/users': 'User Management',
  '/settings': 'Settings',
}

const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/leads', label: 'Leads', icon: Target },
  { path: '/customers', label: 'Customers', icon: Users },
  { path: '/inventory', label: 'Inventory', icon: Package },
  { path: '/orders', label: 'Orders', icon: ClipboardList },
  { path: '/issues', label: 'Issues', icon: AlertTriangle, badgeKey: 'issues' as const },
  { path: '/commissions', label: 'Commissions', icon: DollarSign },
]

const ADMIN_NAV_ITEMS = [
  { path: '/tickets', label: 'Tickets', icon: Headphones },
  { path: '/warranty', label: 'Warranty', icon: Shield },
  { path: '/users', label: 'User Management', icon: UserCog },
  { path: '/settings', label: 'Settings', icon: Settings },
]

function getInitials(name: string) {
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout, access_token } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'
  const pageTitle = ROUTE_TITLES[location.pathname] ?? 'Portal'
  const initials = user?.full_name ? getInitials(user.full_name) : '?'

  // Sidebar issue badge — count of urgent/high open issues. We use the
  // summary endpoint's `recent_urgent` field, which is bounded at 10. If the
  // bound is hit we render "10+" so the user knows it could be more.
  // The fetch re-runs whenever the route changes (cheap and self-refreshing
  // when admins move between pages); a more rigorous approach would be a
  // websocket or polling, but this gets the badge accurate enough.
  const [urgentBadge, setUrgentBadge] = useState<{ count: number; capped: boolean }>(
    { count: 0, capped: false },
  )
  useEffect(() => {
    if (!access_token) return
    let cancelled = false
    ;(async () => {
      try {
        const sum = await apiGet<{ recent_urgent: unknown[] }>(
          '/api/issues/summary', access_token,
        )
        if (cancelled) return
        const list = Array.isArray(sum.recent_urgent) ? sum.recent_urgent : []
        setUrgentBadge({ count: list.length, capped: list.length >= 10 })
      } catch {
        // Best-effort; the badge just stays at its previous value.
      }
    })()
    return () => { cancelled = true }
  }, [access_token, location.pathname])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div className="layout">
      {/* Sidebar */}
      <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
        {/* Logo */}
        <div className="sidebar-logo">
          {!collapsed && (
            <span className="sidebar-logo-text">
              Elixi<span className="logo-x">rX</span>
            </span>
          )}
          <button
            className="sidebar-collapse-btn"
            onClick={() => setCollapsed(c => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        {/* Nav */}
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const showIssueBadge = item.badgeKey === 'issues' && urgentBadge.count > 0
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              >
                <Icon size={18} />
                <span className="nav-label">{item.label}</span>
                {showIssueBadge && !collapsed && (
                  <span className="nav-badge">
                    {urgentBadge.capped ? '10+' : urgentBadge.count}
                  </span>
                )}
              </NavLink>
            )
          })}

          {isAdmin && (
            <>
              <hr className="nav-divider" />
              <div className="nav-section-label">ADMIN</div>
              {ADMIN_NAV_ITEMS.map(({ path, label, icon: Icon }) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                >
                  <Icon size={18} />
                  <span className="nav-label">{label}</span>
                </NavLink>
              ))}
            </>
          )}
        </nav>

        {/* Theme toggle */}
        <div className="sidebar-theme-toggle">
          <button className="theme-toggle-btn" onClick={toggleTheme} aria-label="Toggle theme">
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            <span className="theme-toggle-label">
              {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
            </span>
          </button>
        </div>

        {/* User */}
        <div className="sidebar-user">
          <div className="user-avatar">{initials}</div>
          <div className="user-info">
            <div className="user-name">{user?.full_name}</div>
            <span className="user-role-badge">
              {user?.role?.replace('_', ' ')}
            </span>
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="layout-main">
        {/* Header */}
        <header className="layout-header">
          <h1 className="header-title">{pageTitle}</h1>

          <div className="header-actions">
            <button className="header-bell-btn" aria-label="Notifications">
              <Bell size={20} />
              <span className="notification-badge">0</span>
            </button>

            <div className="header-avatar-wrapper" ref={dropdownRef}>
              <button
                className="header-avatar-btn"
                onClick={() => setDropdownOpen(o => !o)}
                aria-label="User menu"
              >
                <div className="header-avatar">{initials}</div>
              </button>

              {dropdownOpen && (
                <div className="dropdown-menu">
                  <div className="dropdown-user-info">
                    <div className="dropdown-user-name">{user?.full_name}</div>
                    <div className="dropdown-user-email">{user?.email}</div>
                  </div>
                  <button
                    className="dropdown-logout-btn"
                    onClick={() => { setDropdownOpen(false); logout() }}
                  >
                    <LogOut size={14} />
                    Logout
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="layout-content">
          {children}
        </main>
      </div>
    </div>
  )
}
