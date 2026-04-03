import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiPost } from '../lib/api'
import { useAuth } from '../lib/auth'
import './AdminSetup.css'

interface AdminSetupResponse {
  success: boolean
  message: string
  is_first_account: boolean
}

export default function AdminSetup() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [adminCode, setAdminCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const clearError = () => { if (error) setError('') }

  const handleSubmit = async (e: { preventDefault(): void }) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      await apiPost<AdminSetupResponse>('/api/auth/admin-setup', {
        email,
        password,
        full_name: fullName,
        admin_code: adminCode,
      })

      await login(email, password)
      navigate('/dashboard')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-card">
        <div className="admin-logo">
          Elixir<span className="admin-logo-accent">X</span>
        </div>

        <div className="admin-subtitle">Admin Setup</div>

        <form onSubmit={handleSubmit}>
          <div className="admin-field">
            <input
              className="admin-input"
              type="text"
              placeholder="Full name"
              value={fullName}
              onChange={e => { setFullName(e.target.value); clearError() }}
              required
            />
          </div>

          <div className="admin-field">
            <input
              className="admin-input"
              type="email"
              placeholder="Email address"
              value={email}
              onChange={e => { setEmail(e.target.value); clearError() }}
              required
            />
          </div>

          <div className="admin-field">
            <input
              className="admin-input"
              type="password"
              placeholder="Password"
              value={password}
              onChange={e => { setPassword(e.target.value); clearError() }}
              required
            />
          </div>

          <div className="admin-field">
            <input
              className="admin-input"
              type="text"
              placeholder="Admin code"
              value={adminCode}
              onChange={e => { setAdminCode(e.target.value); clearError() }}
              required
            />
          </div>

          <button className="admin-button" type="submit" disabled={loading}>
            {loading ? 'Creating...' : 'Create Admin Account'}
          </button>

          {error && <div className="admin-error">{error}</div>}
        </form>
      </div>

      <div className="admin-back-link">
        <Link to="/login">Back to login</Link>
      </div>
    </div>
  )
}
