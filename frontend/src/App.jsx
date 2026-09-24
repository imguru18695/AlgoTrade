import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Dashboard from './components/Dashboard.jsx'
import { fetchSession } from './api.js'

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [session, setSession] = useState(null)   // null = unknown/no login concept here

  useEffect(() => {
    let alive = true
    fetchSession().then(s => { if (alive) setSession(s) })
    return () => { alive = false }
  }, [])

  return (
    <div className="app-grid" style={{ display: 'grid', gridTemplateColumns: (collapsed ? '66px' : '236px') + ' 1fr', height: '100vh', overflow: 'hidden' }}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} active="dashboard" session={session} />
      <Dashboard />
    </div>
  )
}
