import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiPost } from '../lib/api'
import './Login.css'

interface LoginResponse {
  access_token: string
  token_type: string
}

export default function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const clearError = () => { if (error) setError('') }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const data = await apiPost<LoginResponse>('/api/auth/login', { email, password })
      localStorage.setItem('token', data.access_token)
      navigate('/dashboard')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      if (message.includes('401') || message.toLowerCase().includes('invalid')) {
        setError('Invalid email or password')
      } else if (message.includes('403')) {
        setError('Your account is not active. Contact your administrator.')
      } else {
        setError(message)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          Elixir<span className="login-logo-accent">X</span>
        </div>

        <div className="login-subtitle">Sales Portal</div>

        <form onSubmit={handleSubmit}>
          <div className="login-field">
            <input
              className="login-input"
              type="email"
              placeholder="Email address"
              value={email}
              onChange={e => { setEmail(e.target.value); clearError() }}
            />
          </div>

          <div className="login-field">
            <input
              className="login-input"
              type="password"
              placeholder="Password"
              value={password}
              onChange={e => { setPassword(e.target.value); clearError() }}
            />
          </div>

          <button
            className="login-button"
            type="submit"
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>

          {error && <div className="login-error">{error}</div>}
        </form>
      </div>

      <div className="login-admin-link">
        <Link to="/admin-setup">Admin Setup</Link>
      </div>
    </div>
  )
}
