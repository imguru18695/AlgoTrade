import { n2 } from '../util.js'

function Chip({ sym, value, chg }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '11px 22px', borderRight: '1px solid var(--line)', flex: '1 1 0', minWidth: 170, maxWidth: 300 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 600, letterSpacing: '.02em' }}>{sym}</span>
        <span className="mono" style={{ fontSize: 11, color: chg >= 0 ? 'var(--up)' : 'var(--down)' }}>{chg >= 0 ? '▲' : '▼'} {Math.abs(chg).toFixed(2)}%</span>
      </div>
      <span className="mono" style={{ fontSize: 16, fontWeight: 600, letterSpacing: '-.01em' }}>{n2(value)}</span>
    </div>
  )
}

export default function Ticker({ ticker = [], marketStatus }) {
  const closed = marketStatus?.state !== 'open'
  return (
    <header style={{ display: 'flex', alignItems: 'stretch', borderBottom: '1px solid var(--line)', background: 'var(--panel)' }}>
      {ticker.map(t => <Chip key={t.sym} sym={t.sym} value={t.value} chg={t.chg_pct} />)}
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 18, padding: '0 22px' }}>
        {marketStatus && (
          <span className="mono" style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '.04em', color: closed ? 'var(--down)' : 'var(--up)', background: 'color-mix(in srgb,' + (closed ? 'var(--down)' : 'var(--up)') + ' 12%,transparent)', padding: '4px 10px', borderRadius: 4 }}>
            {closed ? `MARKET CLOSED (${marketStatus.note.toUpperCase()})` : 'MARKET OPEN'}
          </span>
        )}
        {marketStatus && <span className="mono" style={{ fontSize: 11, color: 'var(--muted)' }}>Last Updated: {marketStatus.as_of}</span>}
      </div>
    </header>
  )
}
