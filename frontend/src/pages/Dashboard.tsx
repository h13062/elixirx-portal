import { useAuth } from '../lib/auth'
import './Dashboard.css'

export default function Dashboard() {
  const { user } = useAuth()

  return (
    <div className="dashboard">
      <div className="dashboard-welcome">Welcome back, {user?.full_name}</div>
      <div className="dashboard-subtitle">Here's an overview of your portal activity.</div>
    </div>
  )
}
