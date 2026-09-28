import { useEffect, useRef, useState } from 'react'
import { fetchManagement, fetchPnl, postForm } from '../api.js'
import { isMarketHours } from '../util.js'
import KpiBar from './KpiBar.jsx'
import UnallocatedSection from './UnallocatedSection.jsx'
import BasketCard from './BasketCard.jsx'
import { Button } from './ui.jsx'

const PNL_POLL_MS = 5000

export default function Management() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [pnl, setPnl] = useState(null)
  const hasLoadedRef = useRef(false)

  const refresh = () => fetchManagement()
    .then(d => { setData(d); setError(null); hasLoadedRef.current = true })
    .catch(e => {
      if (!hasLoadedRef.current) setError(e.message)
      else console.warn('management refresh failed, keeping last known data:', e.message)
    })

  useEffect(() => { refresh() }, [])

  // Deliberately separate from the effect above: this ONLY calls /pnl (a
  // cheap in-memory recompute, no Kite API call), never /api/management
  // (which triggers _refresh_cache() — a real Kite REST call). Polling that
  // at 5s instead of /pnl would multiply live Kite call volume ~12x for as
  // long as this tab stays open.
  useEffect(() => {
    if (!data) return
    let alive = true
    const tick = () => {
      if (data.demo_mode || !isMarketHours()) return
      fetchPnl().then(p => { if (alive) setPnl(p) }).catch(e => console.warn('pnl poll failed:', e.message))
    }
    const id = setInterval(tick, PNL_POLL_MS)
    return () => { alive = false; clearInterval(id) }
  }, [data])

  if (error) return <div style={{ padding: 16, color: 'var(--down)', fontSize: 13 }}>Could not load management: {error}</div>
  if (!data) return <div style={{ padding: 16, color: 'var(--muted)', fontSize: 13 }}>Loading…</div>

  return (
    <div style={{ padding: 16, overflow: 'auto', height: '100%' }}>
      <KpiBar
        totalPnl={pnl?.total_pnl ?? data.total_pnl}
        activeBasketsCount={data.active_baskets_count}
        openPositionsCount={data.positions.length}
        noRmCount={data.baskets_without_rm_count}
      />

      <UnallocatedSection unallocated={data.unallocated} baskets={data.baskets} pnlPositions={pnl?.positions} refresh={refresh} />

      {data.baskets.map(b => (
        <BasketCard key={b.id} basket={b} pnlPositions={pnl?.positions} pnlBasket={pnl?.baskets?.[String(b.id)]} refresh={refresh} />
      ))}

      <Button variant="ghost" onClick={() => postForm('/baskets/create', { name: '' }).then(refresh)}>+ New Basket</Button>
    </div>
  )
}
