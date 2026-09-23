import { Card, CardHead, Row, Tag } from './ui.jsx'
import { n0, n2, upc, stateColor, lastSessions } from '../util.js'

const toneColor = t => (t === 'up' ? 'var(--up)' : t === 'down' ? 'var(--down)' : 'var(--amber)')

export default function IndexColumn({ ix }) {
  const dates = lastSessions(5)
  const d = ix.deriv

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
      {/* Historical sessions */}
      <Card>
        <CardHead title={`${ix.name} · Historical Sessions`}
          right={<span className="mono" style={{ fontSize: 11.5, color: 'var(--muted)' }}>SPOT: {n2(ix.value)}</span>} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8, padding: '14px 18px 12px' }}>
          {ix.last5.map((v, i) => {
            const c = upc(v)
            return (
              <div key={i} style={{ textAlign: 'center', border: '1px solid color-mix(in srgb,' + c + ' 35%,transparent)', borderRadius: 6, padding: '9px 4px', background: 'color-mix(in srgb,' + c + ' 8%,transparent)' }}>
                <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 5 }}>{dates[i]}</div>
                <div className="mono" style={{ fontSize: 12, fontWeight: 600, color: c }}>{v >= 0 ? '+' : '−'}{Math.abs(v).toFixed(2)}%</div>
              </div>
            )
          })}
        </div>
        {ix.hist_insight && (
          <div style={{ display: 'flex', gap: 9, padding: '11px 18px', borderTop: '1px solid var(--line)', alignItems: 'baseline' }}>
            <span style={{ fontWeight: 600, color: toneColor(ix.hist_insight.tone), whiteSpace: 'nowrap' }}>{ix.hist_insight.label}</span>
            <span style={{ color: 'var(--muted)', fontSize: 12, lineHeight: 1.5 }}>{ix.hist_insight.detail}</span>
          </div>
        )}
      </Card>

      {/* 52W range */}
      <Card>
        <div style={{ padding: '15px 18px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ fontSize: 10, color: 'var(--muted-2)', letterSpacing: '.12em', textTransform: 'uppercase', fontWeight: 600 }}>52W Range</span>
            <span className="mono" style={{ fontSize: 11.5, color: 'var(--teal)', fontWeight: 600 }}>{ix.w52.pos_pct}%</span>
          </div>
          <div style={{ position: 'relative', height: 6, borderRadius: 3, background: 'linear-gradient(90deg,rgba(248,113,122,.35),var(--line) 50%,rgba(52,211,153,.35))', margin: '18px 0 12px' }}>
            <div style={{ position: 'absolute', top: '50%', left: ix.w52.pos_pct + '%', width: 13, height: 13, borderRadius: '50%', background: 'var(--teal)', border: '2.5px solid var(--panel)', boxShadow: '0 0 8px var(--teal), 0 1px 3px rgba(0,0,0,.5)', transform: 'translate(-50%,-50%)', cursor: 'grab' }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div><div className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{n0(ix.w52.low)}</div><div style={{ fontSize: 10, color: 'var(--muted-2)', marginTop: 1 }}>52W low</div></div>
            <div style={{ textAlign: 'right' }}><div className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{n0(ix.w52.high)}</div><div style={{ fontSize: 10, color: 'var(--muted-2)', marginTop: 1 }}>52W high</div></div>
          </div>
        </div>
      </Card>

      {/* Technicals */}
      <Card>
        <CardHead title={`${ix.name} Technicals`}
          right={<Tag color={stateColor(ix.trend.bias)}>{ix.trend.bias}</Tag>} />
        <div className="rows">
          {[20, 50, 100, 200].map(p => {
            const e = ix.ema[p], above = ix.value >= e, dist = (ix.value - e) / e * 100
            return <Row key={p} label={`EMA ${p}`} value={n0(e)}
              tag={`${above ? '▲' : '▼'} ${dist >= 0 ? '+' : '−'}${Math.abs(dist).toFixed(2)}%`}
              tagColor={above ? 'var(--up)' : 'var(--down)'} />
          })}
          <Row label="RSI (14)" value={ix.rsi.value.toFixed(2)} tag={ix.rsi.label} tagColor={stateColor(ix.rsi.label)} />
          <Row label="MACD (12, 26)" value={ix.macd.value?.toFixed(2)} tag={ix.macd.label} tagColor={stateColor(ix.macd.state)} />
          <Row label="On-Balance Volume" tag={ix.obv.state} tagColor={stateColor(ix.obv.state)} />
          <Row label="A/D Line" tag={ix.ad.state} tagColor={stateColor(ix.ad.state)} />
          <Row label="Stochastic" value={`${ix.stoch.k} / ${ix.stoch.d}`} tag={ix.stoch.state} tagColor={stateColor(ix.stoch.state)} />
        </div>
      </Card>

      {/* Derivatives */}
      <Card>
        <CardHead title={`${ix.name} Derivatives`} sub={`${ix.exchange} Contracts`}
          right={<span className="mono" style={{ fontSize: 11, color: 'var(--muted)' }}>FUT BASIS: <b style={{ color: 'var(--up)' }}>+{d.fut_basis}</b></span>} />
        <div className="rows">
          <Row label="Open Interest (OI)" value={d.oi_total} tag={`${d.oi_chg_pct >= 0 ? '+' : ''}${d.oi_chg_pct}% Change`} tagColor={upc(d.oi_chg_pct)} />
          <Row label="Put-Call Ratio (PCR)" value={d.pcr?.toFixed(2)} tag={d.pcr_label} tagColor={stateColor(d.pcr_label)} />
          <Row label="Max Pain Strike" value={n0(d.max_pain)} tag={`Exp ${d.expiry}`} tagColor="var(--muted)" />
          <Row label="Implied Volatility (IV)" value={`${d.iv}%`} tag={`VIX at ${d.vix}`} tagColor="var(--muted)" />
          <Row label="Active Call OI Cluster" value={`${n0(d.call_cluster.strike)} Strike`} tag={`${d.call_cluster.contracts} Contracts`} tagColor="var(--muted)" />
          <Row label="Active Put OI Cluster" value={`${n0(d.put_cluster.strike)} Strike`} tag={`${d.put_cluster.contracts} Contracts`} tagColor="var(--muted)" />
        </div>
      </Card>
    </div>
  )
}
