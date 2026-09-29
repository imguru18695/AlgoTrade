import { useState } from 'react'
import { Card, Tag, Button } from './ui.jsx'
import PositionsTable from './PositionsTable.jsx'
import RMPanel from './RMPanel.jsx'
import { postForm } from '../api.js'
import { inr, upc } from '../util.js'

const posKey = p => `${p.tradingsymbol}|${p.exchange}|${p.product}`

const STATE_COLOR = { fired: 'var(--down)', 'rm-active': 'var(--teal)', 'no-rm': 'var(--amber)', empty: 'var(--muted)' }

function basketState(b) {
  if (b.fired) return 'fired'
  if (b.rm_enabled) return 'rm-active'
  if (!b.positions.length) return 'empty'
  return 'no-rm'
}

export default function BasketCard({ basket: b, pnlPositions, pnlBasket, refresh }) {
  const [expanded, setExpanded] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const [unallocError, setUnallocError] = useState(null)

  const color = STATE_COLOR[basketState(b)]
  const pnl = pnlBasket?.pnl ?? b.pnl
  const pnlPct = pnlBasket?.pnl_pct ?? b.pnl_pct
  const peakPnl = pnlBasket?.peak_pnl ?? b.peak_pnl
  const psFloor = pnlBasket?.ps_floor ?? b.ps_floor

  const toggle = key => setSelected(s => {
    const next = new Set(s)
    next.has(key) ? next.delete(key) : next.add(key)
    return next
  })
  const toggleAll = checked => setSelected(checked ? new Set(b.positions.map(posKey)) : new Set())

  const setOrderType = async orderType => {
    await postForm(`/baskets/${b.id}/order-type`, { order_type: orderType })
    await refresh()
  }

  const unallocateSelected = async () => {
    if (!selected.size) return
    if (b.rm_enabled) {
      setUnallocError('Deactivate Risk Management before unallocating positions.')
      setTimeout(() => setUnallocError(null), 4000)
      return
    }
    const positions = b.positions.filter(p => selected.has(posKey(p)))
    await postForm('/baskets/unassign-bulk', {
      tradingsymbol: positions.map(p => p.tradingsymbol),
      exchange: positions.map(p => p.exchange),
      product: positions.map(p => p.product),
    })
    setSelected(new Set())
    await refresh()
  }

  return (
    <Card style={{ marginBottom: 12, borderColor: color !== 'var(--muted)' ? `color-mix(in srgb,${color} 35%,var(--line))` : undefined }}>
      <div onClick={() => setExpanded(e => !e)} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 18px', cursor: 'pointer' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 15.5 }}>{b.name}</span>
            {b.fired && <Tag size={12} color="var(--down)">FIRED</Tag>}
            <div style={{ display: 'flex', gap: 4 }}>
              {[['PT', b.rm.pt_active], ['LG', b.rm.lg_active], ['PS', b.rm.ps_active], ['EOD', b.rm.eod_exit]].map(([label, on]) => (
                <span key={label} title={label} style={{ fontSize: 11, fontWeight: 700, padding: '2px 6px', borderRadius: 3,
                  color: on ? 'var(--teal)' : 'var(--muted-2)', background: on ? 'var(--teal-dim)' : 'var(--panel-2)' }}>{label}</span>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {peakPnl != null && <span style={{ fontSize: 12, color: 'var(--muted)' }}>Peak <span className="mono" style={{ color: 'var(--up)' }}>{inr(peakPnl)}</span></span>}
            {psFloor != null && <span style={{ fontSize: 12, color: 'var(--muted)' }}>PS Floor <span className="mono" style={{ color: 'var(--up)' }}>{inr(psFloor)}</span></span>}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="mono" style={{ fontWeight: 700, fontSize: 17, color: upc(pnl) }}>{inr(pnl)}</div>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', marginTop: 3 }}>
            {b.positions.length > 0 && <Tag size={12} color={upc(pnlPct)}>{pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%</Tag>}
            <Tag size={12} color="var(--muted)">{b.positions.length} pos</Tag>
          </div>
        </div>
        <Button variant="ghost" onClick={e => { e.stopPropagation(); setExpanded(true) }}>Edit</Button>
        <span style={{ color: 'var(--muted)', transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}>›</span>
      </div>

      {expanded && (
        <div style={{ borderTop: '1px solid var(--line)', padding: 18, display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)', gap: 20 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <h3 style={{ margin: 0, fontSize: 15 }}>Positions</h3>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <div style={{ display: 'flex', border: '1px solid var(--line-2)', borderRadius: 7, overflow: 'hidden' }}>
                  {['LIMIT', 'MARKET'].map(ot => (
                    <button key={ot} onClick={() => setOrderType(ot)}
                      style={{ padding: '7px 13px', fontSize: 13, fontWeight: 600, cursor: 'pointer', border: 'none',
                        background: b.order_type === ot ? 'var(--teal-dim)' : 'transparent',
                        color: b.order_type === ot ? 'var(--teal)' : 'var(--muted)' }}>{ot === 'LIMIT' ? 'Limit' : 'Market'}</button>
                  ))}
                </div>
                {selected.size > 0 && (
                  <Button variant="danger" onClick={unallocateSelected}>Unallocate Selected ({selected.size})</Button>
                )}
              </div>
            </div>
            {unallocError && <p style={{ color: 'var(--down)', fontSize: 13, marginBottom: 8 }}>{unallocError}</p>}
            <PositionsTable positions={b.positions} pnlPositions={pnlPositions} showProduct={false}
              selected={selected} onToggle={toggle} onToggleAll={toggleAll} />
          </div>
          <RMPanel basket={b} refresh={refresh} />
        </div>
      )}
    </Card>
  )
}
