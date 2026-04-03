import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import './Login.css'

export default function Login() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const clearError = () => { if (error) setError('') }

  const handleSubmit = async (e: { preventDefault(): void }) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      await login(email, password)
      navigate('/dashboard')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      if (message.toLowerCase().includes('not active')) {
        setError('Your account is not active. Contact your administrator.')
      } else if (
        message.toLowerCase().includes('invalid') ||
        message.toLowerCase().includes('password')
      ) {
        setError('Invalid email or password')
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
