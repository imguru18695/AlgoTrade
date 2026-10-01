import { useEffect, useState } from 'react'
import { fetchLogs, postForm } from '../api.js'
import { Button } from './ui.jsx'
import LogEventCard from './LogEventCard.jsx'
import { istNow } from '../util.js'

const fieldLabel = { fontSize: 11.5, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }
const fieldInput = { background: 'var(--panel-2)', border: '1px solid var(--line-2)', borderRadius: 7, color: 'var(--text)', padding: '8px 10px', fontSize: 14 }

const pad = n => String(n).padStart(2, '0')
const toISO = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

// "to" is always today (IST); "from" walks back from today by the given unit —
// matches the backend's own default-range math (today minus 6 days) rather
// than introducing a second, potentially-inconsistent definition of "recent".
function presetRange(days, months) {
  const to = istNow()
  const from = new Date(to.getFullYear(), to.getMonth(), to.getDate())
  if (months) from.setMonth(from.getMonth() - months)
  if (days) from.setDate(from.getDate() - days)
  return { from: toISO(from), to: toISO(to) }
}

const PRESETS = [
  { key: '7d', label: '7D', title: 'Past 7 Days', days: 6 },
  { key: '1m', label: '1M', title: 'Past 1 Month', months: 1 },
  { key: '3m', label: '3M', title: 'Past 3 Months', months: 3 },
]

export default function Logs() {
  const [basketName, setBasketName] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [activePreset, setActivePreset] = useState('7d')  // matches the server's own default range below
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

  useEffect(() => { void load({}) }, [])

  const search = e => {
    e.preventDefault()
    void load({ basketName, fromDate, toDate })
  }

  const applyPreset = ({ key, days, months }) => {
    const { from, to } = presetRange(days, months)
    setActivePreset(key)
    setFromDate(from)
    setToDate(to)
    void load({ basketName, fromDate: from, toDate: to })
  }

  const editDate = setter => e => { setter(e.target.value); setActivePreset(null) }

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
          <input type="date" value={fromDate} onChange={editDate(setFromDate)} style={fieldInput} />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={fieldLabel}>To Date</span>
          <input type="date" value={toDate} onChange={editDate(setToDate)} style={fieldInput} />
        </label>
        <Button type="submit" variant="primary">Search</Button>

        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
          {PRESETS.map(p => (
            <button key={p.key} type="button" title={p.title} onClick={() => applyPreset(p)}
              style={{ padding: '8px 13px', fontSize: 13, fontWeight: 600, borderRadius: 7, cursor: 'pointer',
                background: activePreset === p.key ? 'var(--teal-dim)' : 'transparent',
                color: activePreset === p.key ? 'var(--teal)' : 'var(--muted)',
                border: '1px solid ' + (activePreset === p.key ? 'var(--teal)' : 'var(--line-2)') }}>
              {p.label}
            </button>
          ))}
        </div>
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
