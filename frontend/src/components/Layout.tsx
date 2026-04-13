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
} from 'lucide-react'
import { useAuth } from '../lib/auth'
import './Layout.css'

const ROUTE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/leads': 'Leads',
  '/customers': 'Customers',
  '/inventory': 'Inventory',
  '/orders': 'Orders',
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
  const { user, logout } = useAuth()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'
  const pageTitle = ROUTE_TITLES[location.pathname] ?? 'Portal'
  const initials = user?.full_name ? getInitials(user.full_name) : '?'

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
          {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <Icon size={18} />
              <span className="nav-label">{label}</span>
            </NavLink>
          ))}

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
