import { useAuth } from '../lib/auth'

export default function Dashboard() {
  const { user, logout } = useAuth()

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#0A0F1C',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
    }}>
      <div style={{ color: '#F8FAFC', fontSize: '24px', marginBottom: '8px' }}>
        Welcome, {user?.full_name}
      </div>
      <div style={{ color: '#94A3B8', fontSize: '16px', marginBottom: '32px' }}>
        Role: {user?.role}
      </div>
      <button
        onClick={logout}
        style={{
          padding: '10px 24px',
          backgroundColor: '#1E293B',
          color: '#F8FAFC',
          border: '1px solid #334155',
          borderRadius: '6px',
          cursor: 'pointer',
          fontSize: '14px',
        }}
      >
        Logout
      </button>
    </div>
  )
}
