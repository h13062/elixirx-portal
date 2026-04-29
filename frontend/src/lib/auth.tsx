import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiPost, apiGet, registerAuthFailureHandler } from './api'
import { supabase } from './supabaseClient'

interface User {
  id: string
  email: string
  full_name: string
  role: string
  tier: string | null
  account_status: string
}

interface LoginData {
  access_token: string
  refresh_token: string
  user: User
}

interface AuthContextType {
  user: User | null
  access_token: string | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [access_token, setAccessToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  // ── Auth-failure handoff: api.ts will call this when refresh fails ───
  useEffect(() => {
    registerAuthFailureHandler(() => {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      setUser(null)
      setAccessToken(null)
      navigate('/login')
    })
  }, [navigate])

  // ── On mount: hydrate session from localStorage, then verify with /me ─
  useEffect(() => {
    const access = localStorage.getItem('access_token')
    const refresh = localStorage.getItem('refresh_token')

    if (!access || !refresh) {
      setLoading(false)
      return
    }

    let cancelled = false
    ;(async () => {
      try {
        // Hand the persisted tokens to the supabase client so api.ts can read
        // them via getSession() AND so autoRefreshToken kicks in on a timer.
        await supabase.auth.setSession({
          access_token: access,
          refresh_token: refresh,
        })

        // Verify with backend; api.ts will refresh-and-retry on its own if the
        // access token has already expired by the time we get here.
        const userObj = await apiGet<User>('/api/auth/me')
        if (cancelled) return
        setUser(userObj)
        setAccessToken(access)
      } catch {
        if (cancelled) return
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  // ── Mirror supabase auth events back into our React state + localStorage ─
  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'TOKEN_REFRESHED' && session) {
        localStorage.setItem('access_token', session.access_token)
        localStorage.setItem('refresh_token', session.refresh_token)
        setAccessToken(session.access_token)
      }
      if (event === 'SIGNED_OUT') {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        setUser(null)
        setAccessToken(null)
      }
    })
    return () => data.subscription.unsubscribe()
  }, [])

  const login = async (email: string, password: string) => {
    const data = await apiPost<LoginData>('/api/auth/login', { email, password })
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)

    // Hand both tokens to the supabase client so future fetchWithAuth calls
    // can refresh transparently when the access token expires.
    await supabase.auth.setSession({
      access_token: data.access_token,
      refresh_token: data.refresh_token,
    })

    setAccessToken(data.access_token)
    setUser(data.user)
  }

  const logout = async () => {
    await supabase.auth.signOut().catch(() => {
      /* signOut hits Supabase; ignore network failures, we still clear local state */
    })
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setUser(null)
    setAccessToken(null)
    navigate('/login')
  }

  return (
    <AuthContext.Provider value={{ user, access_token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
