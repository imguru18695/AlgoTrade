import { useState } from 'react'
import { Card, Button } from './ui.jsx'
import PositionsTable from './PositionsTable.jsx'
import BulkAllocateModal from './BulkAllocateModal.jsx'
import { postForm } from '../api.js'

const posKey = p => `${p.tradingsymbol}|${p.exchange}|${p.product}`

export default function UnallocatedSection({ unallocated, baskets, pnlPositions, refresh }) {
  const [selected, setSelected] = useState(new Set())
  const [modalOpen, setModalOpen] = useState(false)

  if (!unallocated.length) return null

  const toggle = key => setSelected(s => {
    const next = new Set(s)
    next.has(key) ? next.delete(key) : next.add(key)
    return next
  })
  const toggleAll = checked => setSelected(checked ? new Set(unallocated.map(posKey)) : new Set())

  const selectedPositions = unallocated.filter(p => selected.has(posKey(p)))

  const submit = async ({ mode, basketId, basketName }) => {
    await postForm('/baskets/assign-bulk', {
      basket_id: mode === 'existing' ? basketId : undefined,
      basket_name: mode === 'new' ? (basketName || '') : undefined,
      tradingsymbol: selectedPositions.map(p => p.tradingsymbol),
      exchange: selectedPositions.map(p => p.exchange),
      product: selectedPositions.map(p => p.product),
      instrument_token: selectedPositions.map(p => p.instrument_token ?? ''),
    })
    setSelected(new Set())
    setModalOpen(false)
    await refresh()
  }

  return (
    <Card style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 18px', borderBottom: '1px solid var(--line)' }}>
        <span style={{ fontWeight: 600, fontSize: 15.5 }}>Unallocated <span style={{ color: 'var(--muted)', fontWeight: 400 }}>({unallocated.length})</span></span>
        {selected.size > 0 && (
          <Button variant="primary" onClick={() => setModalOpen(true)}>Allocate Selected ({selected.size})</Button>
        )}
      </div>
      <div style={{ padding: '4px 18px 14px' }}>
        <PositionsTable positions={unallocated} pnlPositions={pnlPositions} showProduct
          selected={selected} onToggle={toggle} onToggleAll={toggleAll} />
      </div>
      <BulkAllocateModal open={modalOpen} onClose={() => setModalOpen(false)}
        selectedPositions={selectedPositions} baskets={baskets} onSubmit={submit} />
    </Card>
  )
}
