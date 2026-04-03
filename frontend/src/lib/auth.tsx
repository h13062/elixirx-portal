import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiPost, apiGet } from './api'

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

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      setLoading(false)
      return
    }
    apiGet<User>('/api/auth/me', token)
      .then(userObj => {
        setUser(userObj)
        setAccessToken(token)
      })
      .catch(() => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
      })
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    const data = await apiPost<LoginData>('/api/auth/login', { email, password })
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    setAccessToken(data.access_token)
    setUser(data.user)
  }

  const logout = () => {
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
