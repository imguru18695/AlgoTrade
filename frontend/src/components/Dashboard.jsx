import { useEffect, useRef, useState } from 'react'
import { fetchDashboard } from '../api.js'
import Ticker from './Ticker.jsx'
import IndexColumn from './IndexColumn.jsx'
import RightRail from './RightRail.jsx'

// Matches the backend's own quote-cache TTL (market/live.py, market/live_nse.py)
// — polling faster than this would just re-read the same cached values.
const REFRESH_MS = 15000

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const hasLoadedRef = useRef(false)

  useEffect(() => {
    let alive = true
    const load = () => fetchDashboard()
      .then(d => {
        if (!alive) return
        setData(d)
        setError(null)
        hasLoadedRef.current = true
      })
      .catch(e => {
        if (!alive) return
        if (!hasLoadedRef.current) setError(e.message)
        else console.warn('dashboard refresh failed, keeping last known data:', e.message)
      })
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => { alive = false; clearInterval(id) }
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
      <Ticker ticker={data?.ticker || []} marketStatus={data?.market_status} />
      <div style={{ padding: 16, overflow: 'auto', flex: 1 }}>
        {error && <div style={{ color: 'var(--down)', fontSize: 13 }}>Could not load dashboard: {error}</div>}
        {!data && !error && <div style={{ color: 'var(--muted)', fontSize: 13 }}>Loading…</div>}
        {data && (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr) 360px', gap: 14, alignItems: 'start' }}>
            {data.indices.map(ix => <IndexColumn key={ix.key} ix={ix} />)}
            <RightRail globals={data.globals} flows={data.flows} sectors={data.sectors} />
          </div>
        )}
      </div>
    </div>
  )
}
