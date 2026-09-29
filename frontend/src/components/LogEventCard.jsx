import { Card, Tag } from './ui.jsx'
import { inr, upc } from '../util.js'

const STATUS_COLOR = {
  complete: 'var(--up)', placed: 'var(--teal)', rejected: 'var(--down)',
  unknown: 'var(--down)', cancelled: 'var(--amber)', open: 'var(--muted)',
}
const statusColor = s => STATUS_COLOR[(s || 'unknown').toLowerCase().replace(/\s/g, '')] || 'var(--muted)'

const th = { textAlign: 'left', padding: '9px 14px', fontSize: 12, color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em', borderBottom: '1px solid var(--line)', background: 'var(--panel-2)' }
const td = { padding: '10px 14px', fontSize: 14, borderBottom: '1px solid var(--line)', color: 'var(--text-2)' }

function rmChips(rm) {
  const chips = []
  if (rm.pt_active) chips.push(`PT ₹${Math.round(rm.pt_inr).toLocaleString('en-IN')}${rm.pt_ticks ? ` · ${rm.pt_ticks} ticks` : ''}`)
  if (rm.lg_active) chips.push(`LG ₹${Math.round(rm.lg_inr).toLocaleString('en-IN')}${rm.lg_ticks ? ` · ${rm.lg_ticks} ticks` : ''}`)
  if (rm.ps_active) {
    let c = `PS trigger ₹${Math.round(rm.ps_trigger).toLocaleString('en-IN')} · lock ₹${Math.round(rm.ps_lock).toLocaleString('en-IN')}`
    if (rm.ps_step_profit) c += ` · step ₹${Math.round(rm.ps_step_profit).toLocaleString('en-IN')}/₹${Math.round(rm.ps_step_lock).toLocaleString('en-IN')}`
    chips.push(c)
  }
  if (rm.eod_exit) chips.push('EOD Exit enabled')
  return chips
}

export default function LogEventCard({ ev }) {
  const rm = ev.rm_snapshot || {}
  const chips = rmChips(rm)

  return (
    <Card style={{ marginBottom: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, padding: '16px 18px', borderBottom: '1px solid var(--line)' }}>
        <div>
          <div style={{ fontSize: 15.5, fontWeight: 700, marginBottom: 4 }}>{ev.basket_name}</div>
          <div style={{ fontSize: 13, color: 'var(--amber)', fontWeight: 600, marginBottom: 9 }}>{ev.trigger_reason}</div>
          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>Triggered at <span className="mono" style={{ color: 'var(--text)', fontWeight: 500 }}>{ev.triggered_at?.slice(0, 19).replace('T', ' ')} IST</span></span>
            <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>Basket ID <span className="mono" style={{ color: 'var(--text)', fontWeight: 500 }}>#{ev.basket_id}</span></span>
            {ev.mtm_at_trigger != null && (
              <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>MTM at trigger <span className="mono" style={{ color: upc(ev.mtm_at_trigger), fontWeight: 600 }}>{inr(ev.mtm_at_trigger)}</span></span>
            )}
            {ev.peak_pnl != null && (
              <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>Peak P&L <span className="mono" style={{ color: 'var(--up)', fontWeight: 600 }}>{inr(ev.peak_pnl)}</span></span>
            )}
            {ev.ps_floor_at_trigger != null && (
              <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>PS Floor at trigger <span className="mono" style={{ color: 'var(--amber)', fontWeight: 600 }}>{inr(ev.ps_floor_at_trigger)}</span></span>
            )}
          </div>
        </div>
        <Tag size={12} color="var(--muted)">{ev.order_type}</Tag>
      </div>

      {chips.length ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, padding: '12px 18px', background: 'var(--panel-2)', borderBottom: '1px solid var(--line)' }}>
          {chips.map((c, i) => <Tag key={i} size={12.5} color="var(--text-2)">{c}</Tag>)}
        </div>
      ) : (
        <div style={{ padding: '12px 18px', fontSize: 13, color: 'var(--muted)', background: 'var(--panel-2)', borderBottom: '1px solid var(--line)' }}>No RM config at fire time</div>
      )}

      {ev.orders?.length ? (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {['Symbol', 'Exchange', 'Product', 'Side', 'Qty Placed', 'Limit Price', 'Order ID', 'Filled Qty', 'Status', 'Attempt'].map(h => <th key={h} style={th}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {ev.orders.map(o => (
              <tr key={o.id}>
                <td style={{ ...td, color: 'var(--text)', fontWeight: 600 }}>{o.tradingsymbol}</td>
                <td style={td}>{o.exchange}</td>
                <td style={td}>{o.product}</td>
                <td style={{ ...td, color: o.side === 'BUY' ? 'var(--up)' : 'var(--down)', fontWeight: 600 }}>{o.side}</td>
                <td style={td} className="mono">{o.qty_placed}</td>
                <td style={td} className="mono">{o.limit_price ? `₹${Number(o.limit_price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : <span style={{ color: 'var(--muted-2)' }}>Market</span>}</td>
                <td style={{ ...td, fontSize: 12, color: 'var(--muted-2)' }}>{o.order_id || '—'}</td>
                <td style={td} className="mono">{o.filled_qty ?? '—'}</td>
                <td style={{ ...td, color: statusColor(o.status), fontWeight: 600 }}>{o.status || '—'}</td>
                <td style={td}><Tag size={11.5} color="var(--muted)">#{o.attempt}</Tag></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div style={{ padding: '14px 18px', fontSize: 13, color: 'var(--muted)' }}>No order records for this event.</div>
      )}
    </Card>
  )
}
