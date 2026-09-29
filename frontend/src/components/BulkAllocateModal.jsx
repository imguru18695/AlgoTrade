import { useState } from 'react'
import { Button } from './ui.jsx'

export default function BulkAllocateModal({ open, onClose, count, baskets, onSubmit }) {
  const [tab, setTab] = useState('existing')
  const [basketId, setBasketId] = useState(baskets[0]?.id ?? '')
  const [basketName, setBasketName] = useState('')
  const [error, setError] = useState(null)

  if (!open) return null

  const submit = () => {
    if (tab === 'existing') {
      const target = baskets.find(b => String(b.id) === String(basketId))
      if (target?.rm_enabled) {
        setError('Deactivate Risk Management on this basket before adding positions.')
        setTimeout(() => setError(null), 4000)
        return
      }
      onSubmit({ mode: 'existing', basketId })
    } else {
      onSubmit({ mode: 'new', basketName })
    }
  }

  return (
    <div onClick={e => e.target === e.currentTarget && onClose()}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}>
      <div style={{ background: 'var(--panel)', border: '1px solid var(--line-2)', borderRadius: 12, padding: 22, width: 340 }}>
        <h3 style={{ margin: '0 0 4px', fontSize: 17 }}>Allocate Selected</h3>
        <p style={{ margin: '0 0 14px', fontSize: 14, color: 'var(--muted)' }}>{count} position{count !== 1 ? 's' : ''} selected</p>

        <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
          {['existing', 'new'].map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ flex: 1, padding: '8px 0', fontSize: 13.5, fontWeight: 600, borderRadius: 7, cursor: 'pointer',
                background: tab === t ? 'var(--teal-dim)' : 'transparent',
                color: tab === t ? 'var(--teal)' : 'var(--muted)',
                border: '1px solid ' + (tab === t ? 'var(--teal)' : 'var(--line-2)') }}>
              {t === 'existing' ? 'Existing Basket' : 'New Basket'}
            </button>
          ))}
        </div>

        {tab === 'existing' ? (
          <select value={basketId} onChange={e => setBasketId(e.target.value)} aria-label="Select existing basket"
            style={{ width: '100%', padding: '10px 11px', borderRadius: 7, background: 'var(--panel-2)', border: '1px solid var(--line-2)', color: 'var(--text)', fontSize: 14 }}>
            {baskets.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        ) : (
          <input type="text" value={basketName} onChange={e => setBasketName(e.target.value)} placeholder="Basket name (optional)"
            aria-label="New basket name"
            style={{ width: '100%', padding: '10px 11px', borderRadius: 7, background: 'var(--panel-2)', border: '1px solid var(--line-2)', color: 'var(--text)', fontSize: 14, boxSizing: 'border-box' }} />
        )}

        {error && <p style={{ color: 'var(--down)', fontSize: 13, marginTop: 8 }}>{error}</p>}

        <Button variant="primary" onClick={submit} style={{ width: '100%', marginTop: 16 }}>
          {tab === 'existing' ? 'Allocate' : 'Create & Allocate'}
        </Button>
        <Button variant="ghost" onClick={onClose} style={{ width: '100%', marginTop: 8 }}>Cancel</Button>
      </div>
    </div>
  )
}
