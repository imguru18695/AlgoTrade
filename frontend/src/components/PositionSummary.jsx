import { Card } from './ui.jsx'
import { inr, n0 } from '../util.js'

const Row = ({ label, value, color, sub }) => (
  <div>
    <div style={{ fontSize: 11, color: 'var(--muted)' }}>{label}</div>
    <div className="mono" style={{ fontSize: 14, fontWeight: 600, color: color || 'var(--text)' }}>{value}</div>
    {sub && <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 1 }}>{sub}</div>}
  </div>
)

const grid = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }
const cardHead = { fontWeight: 600, fontSize: 14, marginBottom: 10 }

// Spot levels where the at-expiry P&L curve crosses zero - the "always"/
// "never" modes have no crossings at all (profitable or not everywhere in
// the scenario range), so there's nothing to list for those.
function breakevenLine(be) {
  if (!be) return '—'
  if (be.mode === 'always') return 'Profitable across the range'
  if (be.mode === 'never') return 'Not profitable across the range'
  return be.levels.map(v => n0(v)).join(' · ') || '—'
}

export default function PositionSummary({ analytics }) {
  if (!analytics) {
    return (
      <Card style={{ padding: 15 }}>
        <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>
          No option legs to analyze — needs at least one option position and a live spot for this underlying.
        </div>
      </Card>
    )
  }

  const { greeks, profile, pcr, max_profit, max_loss, pop, net_premium, atm_iv_pct, breakevens } = analytics

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <Card style={{ padding: 14 }}>
        <div style={cardHead}>Summary</div>
        <div style={grid}>
          <Row label="Max Profit" value={max_profit == null ? 'Unlimited' : inr(max_profit)} color="var(--up)" />
          <Row label="Max Loss" value={max_loss == null ? 'Unlimited' : inr(Math.abs(max_loss))} color="var(--down)" />
          <Row label="Net Premium" value={inr(Math.abs(net_premium))} sub={net_premium >= 0 ? 'credit received' : 'debit paid'} />
          <Row label="Prob. of Profit" value={pop != null ? pop + '%' : '—'} sub={`at ${atm_iv_pct}% vol`} />
        </div>
      </Card>

      <Card style={{ padding: 14 }}>
        <div style={cardHead}>Breakeven at Expiry</div>
        <div style={{ fontSize: 13.5 }} className="mono">{breakevenLine(breakevens?.expiry)}</div>
      </Card>

      <Card style={{ padding: 14 }}>
        <div style={cardHead}>Position Greeks</div>
        <div style={grid}>
          <Row label="Delta" value={greeks.delta.toFixed(2)} />
          <Row label="Gamma" value={greeks.gamma.toFixed(4)} />
          <Row label="Theta" value={greeks.theta.toFixed(2)} color={greeks.theta > 0 ? 'var(--up)' : greeks.theta < 0 ? 'var(--down)' : undefined} />
          <Row label="Vega" value={greeks.vega.toFixed(2)} />
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 10 }}>{profile.label}</div>
      </Card>

      <Card style={{ padding: 14 }}>
        <div style={cardHead}>Put–Call Ratio</div>
        <div style={grid}>
          <Row label="By Premium" value={pcr.by_premium ?? '—'} />
          <Row label="By Quantity" value={pcr.by_quantity ?? '—'} />
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 10 }}>{pcr.skew}</div>
      </Card>
    </div>
  )
}
