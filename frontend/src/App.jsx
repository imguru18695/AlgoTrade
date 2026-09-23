import { useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Dashboard from './components/Dashboard.jsx'

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  return (
    <div className="app-grid" style={{ display: 'grid', gridTemplateColumns: (collapsed ? '66px' : '236px') + ' 1fr', height: '100vh', overflow: 'hidden' }}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} active="dashboard" />
      <Dashboard />
    </div>
  )
}
