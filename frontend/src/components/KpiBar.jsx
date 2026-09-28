import { Card } from './ui.jsx'
import { inr, upc } from '../util.js'

function Kpi({ value, label, color }) {
  return (
    <Card style={{ flex: 1, padding: '14px 18px', textAlign: 'center' }}>
      <div className="mono" style={{ fontSize: 20, fontWeight: 700, color: color || 'var(--text)' }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>{label}</div>
    </Card>
  )
}

export default function KpiBar({ totalPnl, activeBasketsCount, openPositionsCount, noRmCount }) {
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
      <Kpi value={inr(totalPnl)} label="Total MTM P&L" color={upc(totalPnl)} />
      <Kpi value={activeBasketsCount} label="Active Baskets" />
      <Kpi value={openPositionsCount} label="Open Positions" />
      <Kpi value={noRmCount} label="No RM Setup" color={noRmCount > 0 ? 'var(--amber)' : undefined} />
    </div>
  )
}
