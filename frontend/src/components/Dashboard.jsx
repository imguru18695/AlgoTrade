import { useEffect, useState } from 'react'
import { fetchDashboard } from '../api.js'
import Ticker from './Ticker.jsx'
import IndexColumn from './IndexColumn.jsx'
import RightRail from './RightRail.jsx'

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    fetchDashboard().then(d => { if (alive) setData(d) }).catch(e => { if (alive) setError(e.message) })
    return () => { alive = false }
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
