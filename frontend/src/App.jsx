import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Dashboard from './components/Dashboard.jsx'
import Management from './components/Management.jsx'
import Logs from './components/Logs.jsx'
import { fetchSession } from './api.js'

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [session, setSession] = useState(null)   // null = unknown/no login concept here
  const [page, setPage] = useState('dashboard')  // no router today — see Sidebar's NAVIGABLE set

  useEffect(() => {
    let alive = true
    void fetchSession().then(s => { if (alive) setSession(s) })
    return () => { alive = false }
  }, [])

  return (
    <div className="app-grid" style={{ display: 'grid', gridTemplateColumns: (collapsed ? '66px' : '236px') + ' 1fr', height: '100vh', overflow: 'hidden' }}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} active={page} onNavigate={setPage} session={session} />
      {page === 'management' ? <Management /> : page === 'logs' ? <Logs /> : <Dashboard />}
    </div>
  )
}
