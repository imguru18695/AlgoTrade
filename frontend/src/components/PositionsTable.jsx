import { Tag } from './ui.jsx'
import { n2, upc } from '../util.js'

const posKey = p => `${p.tradingsymbol}|${p.exchange}|${p.product}`

const th = { textAlign: 'left', padding: '9px 12px', fontSize: 12, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em', borderBottom: '1px solid var(--line)' }
const td = { padding: '10px 12px', fontSize: 14, borderBottom: '1px solid var(--line)' }

export default function PositionsTable({ positions, pnlPositions, showProduct, selected, onToggle, onToggleAll }) {
  if (!positions.length) return <p style={{ color: 'var(--muted)', fontSize: 14, padding: '14px 4px' }}>No positions.</p>

  const allChecked = positions.length > 0 && positions.every(p => selected.has(posKey(p)))

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th style={{ ...th, width: 30 }}>
            <input type="checkbox" checked={allChecked} onChange={e => onToggleAll(e.target.checked)} aria-label="Select all positions" />
          </th>
          <th style={th}>Symbol</th>
          {showProduct && <th style={th}>Product</th>}
          <th style={th}>Qty</th>
          <th style={th}>Avg Price</th>
          <th style={th}>LTP</th>
          <th style={{ ...th, textAlign: 'right' }}>MTM P&L</th>
        </tr>
      </thead>
      <tbody>
        {positions.map(p => {
          const key = posKey(p)
          const live = pnlPositions?.[key]
          const ltp = live?.ltp ?? p.last_price
          const pnl = live?.pnl ?? p.pnl
          const pnlPct = live?.pnl_pct ?? p.pnl_pct
          return (
            <tr key={key}>
              <td style={td}><input type="checkbox" checked={selected.has(key)} onChange={() => onToggle(key)} aria-label={`Select ${p.tradingsymbol}`} /></td>
              <td style={td}>{p.tradingsymbol}<br /><span style={{ fontSize: 12, color: 'var(--muted)' }}>{p.exchange}</span></td>
              {showProduct && <td style={td}>{p.product}</td>}
              <td style={{ ...td, color: p.quantity > 0 ? 'var(--up)' : 'var(--down)' }} className="mono">{p.quantity > 0 ? '+' : ''}{p.quantity}</td>
              <td style={td} className="mono">{n2(p.average_price)}</td>
              <td style={td} className="mono">{n2(ltp)}</td>
              <td style={{ ...td, textAlign: 'right' }}>
                <span className="mono" style={{ color: upc(pnl), fontWeight: 600 }}>{pnl >= 0 ? '+' : '−'}₹{Math.abs(Math.round(pnl)).toLocaleString('en-IN')}</span>{' '}
                <Tag size={12} color={upc(pnlPct)}>{pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%</Tag>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
