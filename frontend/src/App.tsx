import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'

function AdminSetup() {
  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#0A0F1C',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#F8FAFC',
      fontSize: '18px',
    }}>
      Admin Setup - Coming Soon
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/admin-setup" element={<AdminSetup />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
