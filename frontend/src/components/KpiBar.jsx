import { Icon } from './icons.jsx'
import { inr, upc } from '../util.js'

function Kpi({ icon, value, label, accent, valueColor }) {
  return (
    <div className="fadein" style={{ flex: 1, position: 'relative', overflow: 'hidden', background: 'var(--panel)',
      border: '1px solid var(--line)', borderRadius: 12, padding: '17px 20px' }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: accent }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 12 }}>
        <span style={{ width: 28, height: 28, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: accent, background: 'color-mix(in srgb,' + accent + ' 16%,transparent)', flexShrink: 0 }}>
          <Icon name={icon} size={16} />
        </span>
        <span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 600 }}>{label}</span>
      </div>
      <div className="mono" style={{ fontSize: 28, fontWeight: 700, color: valueColor || 'var(--text)', letterSpacing: '-.01em' }}>{value}</div>
    </div>
  )
}

export default function KpiBar({ totalPnl, activeBasketsCount, openPositionsCount, noRmCount }) {
  const pnlColor = upc(totalPnl)
  const warnColor = noRmCount > 0 ? 'var(--amber)' : 'var(--muted-2)'
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
      <Kpi icon="pnl" value={inr(totalPnl)} label="Total MTM P&L" accent={pnlColor} valueColor={pnlColor} />
      <Kpi icon="basket" value={activeBasketsCount} label="Active Baskets" accent="var(--teal)" />
      <Kpi icon="positions" value={openPositionsCount} label="Open Positions" accent="var(--teal)" />
      <Kpi icon="warning" value={noRmCount} label="No RM Setup" accent={warnColor} valueColor={warnColor} />
    </div>
  )
}
