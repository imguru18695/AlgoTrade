import { Icon } from './icons.jsx'

const NAV = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'management', label: 'Management' },
  { key: 'logs', label: 'Logs' },
  { key: 'strategy', label: 'Strategy' },
  { key: 'execution', label: 'Execution' },
]

function NavItem({ icon, label, active, collapsed }) {
  return (
    <div className="nav-item" title={collapsed ? label : undefined}
      style={{ display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'flex-start', gap: 12,
        padding: collapsed ? '11px 0' : '10px 12px', borderRadius: 7, cursor: 'pointer',
        color: active ? 'var(--text)' : 'var(--muted)', background: active ? 'var(--teal-dim)' : 'transparent',
        boxShadow: active ? 'inset 0 0 0 1px rgba(45,212,191,.25)' : 'none', fontWeight: active ? 600 : 500 }}>
      <span style={{ width: 18, height: 18, display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: active ? 'var(--teal)' : 'var(--muted)', flexShrink: 0 }}><Icon name={icon} /></span>
      <span className="nav-label" style={{ opacity: collapsed ? 0 : 1, width: collapsed ? 0 : 'auto' }}>{label}</span>
    </div>
  )
}

export default function Sidebar({ collapsed, onToggle, active = 'dashboard', session = null }) {
  // session === null means "unknown" (still loading, or this backend has no
  // login concept at all, e.g. demo.py) — keep the original display as-is
  // rather than guess. Only render Login/Logout once we actually know.
  const known = session !== null
  const loggedIn = known && session.logged_in
  const dotColor = !known ? 'var(--up)' : (loggedIn ? 'var(--up)' : 'var(--down)')
  const statusLabel = !known ? 'Live' : (loggedIn ? 'Live' : 'Not connected')

  return (
    <aside style={{ background: 'var(--panel)', borderRight: '1px solid var(--line)', padding: collapsed ? '18px 10px' : '18px 14px',
      display: 'flex', flexDirection: 'column', gap: 22, overflowY: 'auto', overflowX: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: collapsed ? 0 : '0 4px', flexDirection: collapsed ? 'column' : 'row' }}>
        <div style={{ width: 34, height: 34, borderRadius: 9, background: 'linear-gradient(135deg,var(--teal),#0e9488)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 17, flexShrink: 0 }}>◈</div>
        {!collapsed && <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: '.01em' }}>Convexity</div>
          <div style={{ fontSize: 9.5, color: 'var(--muted)', letterSpacing: '.22em' }}>SYSTEMS</div>
        </div>}
        <button className="side-toggle" onClick={onToggle} title={collapsed ? 'Expand' : 'Collapse'}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          style={{ width: 26, height: 26, borderRadius: 7, border: '1px solid var(--line)', background: 'transparent',
            color: 'var(--muted)', cursor: 'pointer', fontSize: 14, lineHeight: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {NAV.map(n => <NavItem key={n.key} icon={n.key} label={n.label} active={n.key === active} collapsed={collapsed} />)}
      </nav>

      <div style={{ marginTop: 'auto', padding: collapsed ? 0 : '0 4px' }}>
        {collapsed ? (
          <div title={`Zerodha Kite · ${statusLabel}`} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: dotColor, boxShadow: `0 0 7px ${dotColor}` }} />
            {known && (
              <a href={loggedIn ? '/auth/logout' : '/auth/login'} title={loggedIn ? 'Logout' : 'Log in'}
                style={{ color: 'var(--muted)', display: 'flex' }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                  <polyline points={loggedIn ? "16 17 21 12 16 7" : "16 7 21 12 16 17"}/>
                  <line x1="21" y1="12" x2="9" y2="12"/>
                </svg>
              </a>
            )}
          </div>
        ) : (
          <>
            <div style={{ fontSize: 10, color: 'var(--muted-2)', letterSpacing: '.12em', marginBottom: 11 }}>BROKER SESSION</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 9 }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: dotColor, boxShadow: `0 0 7px ${dotColor}`, flexShrink: 0 }} />
              <span style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--text)' }}>Zerodha Kite</span>
              <span style={{ marginLeft: 'auto', fontSize: 10.5, fontWeight: 600, color: dotColor, background: `color-mix(in srgb,${dotColor} 12%,transparent)`, padding: '1px 7px', borderRadius: 4 }}>{statusLabel}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--muted)', marginBottom: 5 }}>Client <span className="mono" style={{ color: 'var(--text-2)' }}>AB1234</span></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--muted)', marginBottom: known ? 12 : 0 }}>Latency <span className="mono" style={{ color: 'var(--up)' }}>12.4 ms</span></div>
            {known && (
              <a href={loggedIn ? '/auth/logout' : '/auth/login'}
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, fontSize: 12, fontWeight: 500,
                  color: 'var(--text-2)', background: 'var(--panel-2)', border: '1px solid var(--line-2)', borderRadius: 7,
                  padding: '8px', textDecoration: 'none' }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                  <polyline points={loggedIn ? "16 17 21 12 16 7" : "16 7 21 12 16 17"}/>
                  <line x1="21" y1="12" x2="9" y2="12"/>
                </svg>
                {loggedIn ? 'Logout' : 'Log in'}
              </a>
            )}
          </>
        )}
      </div>
    </aside>
  )
}
