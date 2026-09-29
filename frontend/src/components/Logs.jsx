import { useEffect, useState } from 'react'
import { fetchLogs, postForm } from '../api.js'
import { Button } from './ui.jsx'
import LogEventCard from './LogEventCard.jsx'

const fieldLabel = { fontSize: 11.5, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }
const fieldInput = { background: 'var(--panel-2)', border: '1px solid var(--line-2)', borderRadius: 7, color: 'var(--text)', padding: '8px 10px', fontSize: 14 }

export default function Logs() {
  const [basketName, setBasketName] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = params => fetchLogs(params)
    .then(d => {
      setData(d)
      setError(null)
      // Server fills in the default 7-day range when dates are blank —
      // sync the filter inputs to show the range actually applied.
      setFromDate(d.from_date)
      setToDate(d.to_date)
    })
    .catch(e => setError(e.message))

  useEffect(() => { load({}) }, [])

  const search = e => {
    e.preventDefault()
    load({ basketName, fromDate, toDate })
  }

  const clearShown = async () => {
    if (!data?.events?.length) return
    if (!window.confirm(`Clear ${data.events.length} exit event${data.events.length !== 1 ? 's' : ''} from the log? This cannot be undone.`)) return
    await postForm('/logs/clear', {
      basket_name: basketName,
      from_date: fromDate,
      to_date: toDate,
      event_id: data.events.map(ev => ev.id),
    })
    await load({ basketName, fromDate, toDate })
  }

  if (error) return <div style={{ padding: 16, color: 'var(--down)', fontSize: 14.5 }}>Could not load logs: {error}</div>
  if (!data) return <div style={{ padding: 16, color: 'var(--muted)', fontSize: 14.5 }}>Loading…</div>

  return (
    <div style={{ padding: 16, overflow: 'auto', height: '100%' }}>
      <form onSubmit={search} style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap',
        background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '16px 18px', marginBottom: 18 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={fieldLabel}>Basket</span>
          <select value={basketName} onChange={e => setBasketName(e.target.value)} style={{ ...fieldInput, minWidth: 170 }}>
            <option value="">All Baskets</option>
            {data.basket_names.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={fieldLabel}>From Date</span>
          <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} style={fieldInput} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={fieldLabel}>To Date</span>
          <input type="date" value={toDate} onChange={e => setToDate(e.target.value)} style={fieldInput} />
        </label>
        <Button type="submit" variant="primary">Search</Button>
      </form>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <span style={{ fontSize: 13.5, color: 'var(--muted)' }}>{data.events.length} exit event{data.events.length !== 1 ? 's' : ''} found</span>
        {data.events.length > 0 && <Button variant="danger" onClick={clearShown}>Clear Shown Results</Button>}
      </div>

      {data.events.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--muted)', fontSize: 14 }}>No exit events found for the selected filters.</div>
      ) : (
        data.events.map(ev => <LogEventCard key={ev.id} ev={ev} />)
      )}
    </div>
  )
}
