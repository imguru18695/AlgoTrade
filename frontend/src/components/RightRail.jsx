import { Card, CardHead, Row } from './ui.jsx'
import { cr, upc, n2 } from '../util.js'

export default function RightRail({ globals, flows, sectors }) {
  const b = flows?.breadth?.adv != null && flows?.breadth?.dec != null ? flows.breadth : null
  const advPct = b ? (b.adv / (b.adv + b.dec)) * 100 : 50

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Global markets */}
      <Card>
        <CardHead title="Global Markets" />
        <div className="rows">
          {(globals || []).map(g => (
            <Row key={g.name} label={g.name}
              value={g.value != null
                ? <span>{n2(g.value)}<span style={{ color: 'var(--muted)', fontWeight: 400, marginLeft: 4, fontSize: 11 }}>{g.unit}</span></span>
                : '—'}
              tag={g.chg_pct != null ? `${g.chg_pct >= 0 ? '+' : '−'}${Math.abs(g.chg_pct).toFixed(2)}%` : undefined}
              tagColor={g.chg_pct != null ? upc(g.chg_pct) : undefined} />
          ))}
        </div>
      </Card>

      {/* Institutional & market flows */}
      <Card>
        <CardHead title="Institutional & Market Flows" />
        <div className="rows">
          <Row label="FII Net Position" value={flows?.fii != null ? cr(flows.fii) : '—'} valueColor={flows?.fii != null ? upc(flows.fii) : undefined} />
          <Row label="DII Net Position" value={flows?.dii != null ? cr(flows.dii) : '—'} valueColor={flows?.dii != null ? upc(flows.dii) : undefined} />
          <Row label="Combined Net Inflow" value={flows?.combined != null ? cr(flows.combined) : '—'} valueColor={flows?.combined != null ? upc(flows.combined) : undefined} />
        </div>
        <div style={{ padding: '14px 18px', borderTop: '1px solid var(--line)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 9 }}>
            <span style={{ color: 'var(--muted)' }}>Market Breadth (NSE)</span>
            <span className="mono" style={{ fontWeight: 600 }}>{b ? `${b.adv} Adv / ${b.dec} Dec` : '—'}</span>
          </div>
          <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', opacity: b ? 1 : 0.3 }}>
            <div style={{ width: advPct + '%', background: 'var(--up)' }} />
            <div style={{ width: (100 - advPct) + '%', background: 'var(--down)' }} />
          </div>
        </div>
      </Card>

      {/* Top sector movements */}
      <Card>
        <CardHead title="Top Sector Movements" />
        <div className="rows">
          {(sectors || []).map(s => (
            <Row key={s.name}
              label={<span style={{ display: 'inline-flex', alignItems: 'center', gap: 9 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: s.chg != null ? upc(s.chg) : 'var(--muted)' }} />{s.name}</span>}
              value={s.chg != null ? `${s.chg >= 0 ? '+' : '−'}${Math.abs(s.chg).toFixed(2)}%` : '—'}
              valueColor={s.chg != null ? upc(s.chg) : undefined} />
          ))}
        </div>
      </Card>

      {/* Risk statement */}
      <Card>
        <div style={{ padding: '14px 18px' }}>
          <div style={{ fontSize: 10, color: 'var(--muted-2)', letterSpacing: '.12em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 8 }}>Risk Management Statement</div>
          <p style={{ margin: 0, fontSize: 11.5, color: 'var(--muted)', lineHeight: 1.6 }}>
            Convexity strategy systems use high-fidelity simulation. Past performance of indices does not warrant guaranteed derivative yields. Max-leverage triggers are strictly applied in NSE-BSE routing.
          </p>
        </div>
      </Card>
    </div>
  )
}
