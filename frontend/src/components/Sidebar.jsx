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

export default function Sidebar({ collapsed, onToggle, active = 'dashboard' }) {
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
          <div title="Zerodha Kite · Live · 12.4 ms" style={{ display: 'flex', justifyContent: 'center' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--up)', boxShadow: '0 0 7px var(--up)' }} />
          </div>
        ) : (
          <>
            <div style={{ fontSize: 10, color: 'var(--muted-2)', letterSpacing: '.12em', marginBottom: 11 }}>BROKER SESSION</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 9 }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--up)', boxShadow: '0 0 7px var(--up)', flexShrink: 0 }} />
              <span style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--text)' }}>Zerodha Kite</span>
              <span style={{ marginLeft: 'auto', fontSize: 10.5, fontWeight: 600, color: 'var(--up)', background: 'color-mix(in srgb,var(--up) 12%,transparent)', padding: '1px 7px', borderRadius: 4 }}>Live</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--muted)', marginBottom: 5 }}>Client <span className="mono" style={{ color: 'var(--text-2)' }}>AB1234</span></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: 'var(--muted)' }}>Latency <span className="mono" style={{ color: 'var(--up)' }}>12.4 ms</span></div>
          </>
        )}
      </div>
    </aside>
  )
}
