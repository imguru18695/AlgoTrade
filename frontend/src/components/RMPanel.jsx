import { useEffect, useState } from 'react'
import { Card, Toggle, NumberField, Button } from './ui.jsx'
import RmTwoFieldCard from './RmTwoFieldCard.jsx'
import { postForm } from '../api.js'
import { detectUnderlying } from '../util.js'

function validatePT(inr) {
  if (!inr || inr <= 0) { window.alert('Profit Target: INR Value must be a positive number.'); return false }
  return true
}

function validateSpotGuard({ lower, upper }) {
  if (!lower || !upper || lower <= 0 || upper <= 0) { window.alert('Spot Range Guard: both limits must be positive numbers.'); return false }
  if (Number(lower) >= Number(upper)) { window.alert('Spot Range Guard: Lower limit must be less than Upper limit.'); return false }
  return true
}

function validateVelocityGuard({ pct, minutes }) {
  if (!pct || pct <= 0) { window.alert('Spot Velocity Guard: % Change must be a positive number.'); return false }
  if (!minutes || minutes <= 0) { window.alert('Spot Velocity Guard: Time Window must be a positive number of minutes.'); return false }
  return true
}

function validatePS({ trigger, lock, stepProfit, stepLock, ptInr }) {
  const t = trigger || 0, l = lock || 0, sp = stepProfit || 0, sl = stepLock || 0, pt = ptInr || 0
  if (t <= 0 || l <= 0) { window.alert('Profit Shield: All INR values must be positive.'); return false }
  if (pt > 0 && t > pt) {
    window.alert(`Profit Shield: "If profit reaches" (₹${t.toLocaleString()}) cannot exceed Profit Target (₹${pt.toLocaleString()}).`)
    return false
  }
  if (l > t) {
    window.alert(`Profit Shield: "Lock min profit" (₹${l.toLocaleString()}) must be ≤ "If profit reaches" (₹${t.toLocaleString()}).`)
    return false
  }
  if (sp > 0 && pt > 0 && (t + sp) >= pt) {
    window.alert(`Profit Shield: Trigger + Step (₹${(t + sp).toLocaleString()}) must be less than Profit Target (₹${pt.toLocaleString()}).`)
    return false
  }
  if (sl > 0 && sp > 0 && (l + sl) >= (t + sp)) {
    window.alert(`Profit Shield: Lock + Step Lock (₹${(l + sl).toLocaleString()}) must be less than Trigger + Step Profit (₹${(t + sp).toLocaleString()}).`)
    return false
  }
  return true
}

export default function RMPanel({ basket, refresh }) {
  const rm = basket.rm
  const [pt, setPt] = useState({ active: rm.pt_active, inr: rm.pt_inr, ticks: rm.pt_ticks })
  const [lg, setLg] = useState({ active: rm.lg_active, inr: rm.lg_inr, ticks: rm.lg_ticks })
  const [ps, setPs] = useState({ active: rm.ps_active, trigger: rm.ps_trigger, lock: rm.ps_lock, stepProfit: rm.ps_step_profit, stepLock: rm.ps_step_lock })
  const [spotGuard, setSpotGuard] = useState({ active: rm.spot_guard_active, lower: rm.spot_lower, upper: rm.spot_upper, ticks: rm.spot_guard_ticks })
  const [velocityGuard, setVelocityGuard] = useState({ active: rm.velocity_guard_active, pct: rm.velocity_pct, minutes: rm.velocity_minutes })
  const [eod, setEod] = useState(!!rm.eod_exit)
  const [dof, setDof] = useState(!!(rm.delete_on_fire ?? 1))
  const [name, setName] = useState(basket.name)

  // Resync each draft only when its OWN saved fields change (this card's own
  // successful save, or a fresh basket load) — an unrelated poll tick or a
  // different basket's mutation never touches these exact values, so an
  // in-progress edit here can never be silently overwritten.
  useEffect(() => setPt({ active: rm.pt_active, inr: rm.pt_inr, ticks: rm.pt_ticks }),
    [rm.pt_active, rm.pt_inr, rm.pt_ticks])
  useEffect(() => setLg({ active: rm.lg_active, inr: rm.lg_inr, ticks: rm.lg_ticks }),
    [rm.lg_active, rm.lg_inr, rm.lg_ticks])
  useEffect(() => setPs({ active: rm.ps_active, trigger: rm.ps_trigger, lock: rm.ps_lock, stepProfit: rm.ps_step_profit, stepLock: rm.ps_step_lock }),
    [rm.ps_active, rm.ps_trigger, rm.ps_lock, rm.ps_step_profit, rm.ps_step_lock])
  useEffect(() => setSpotGuard({ active: rm.spot_guard_active, lower: rm.spot_lower, upper: rm.spot_upper, ticks: rm.spot_guard_ticks }),
    [rm.spot_guard_active, rm.spot_lower, rm.spot_upper, rm.spot_guard_ticks])
  useEffect(() => setVelocityGuard({ active: rm.velocity_guard_active, pct: rm.velocity_pct, minutes: rm.velocity_minutes }),
    [rm.velocity_guard_active, rm.velocity_pct, rm.velocity_minutes])
  useEffect(() => setEod(!!rm.eod_exit), [rm.eod_exit])
  useEffect(() => setDof(!!(rm.delete_on_fire ?? 1)), [rm.delete_on_fire])
  useEffect(() => setName(basket.name), [basket.name])

  const savePT = async () => {
    if (!validatePT(pt.inr)) return
    await postForm(`/baskets/${basket.id}/rm/profit-target`, {
      active: pt.active ? '1' : '0',
      inr: pt.active ? pt.inr : undefined,
      ticks: pt.active ? pt.ticks : undefined,
    })
    await refresh()
  }
  const saveLG = async () => {
    await postForm(`/baskets/${basket.id}/rm/loss-guard`, {
      active: lg.active ? '1' : '0',
      inr: lg.active ? lg.inr : undefined,
      ticks: lg.active ? lg.ticks : undefined,
    })
    await refresh()
  }
  const saveSpotGuard = async () => {
    if (!validateSpotGuard(spotGuard)) return
    await postForm(`/baskets/${basket.id}/rm/spot-guard`, {
      active: spotGuard.active ? '1' : '0',
      lower: spotGuard.active ? spotGuard.lower : undefined,
      upper: spotGuard.active ? spotGuard.upper : undefined,
      ticks: spotGuard.active ? spotGuard.ticks : undefined,
    })
    await refresh()
  }
  const saveVelocityGuard = async () => {
    if (!validateVelocityGuard(velocityGuard)) return
    await postForm(`/baskets/${basket.id}/rm/velocity-guard`, {
      active: velocityGuard.active ? '1' : '0',
      pct: velocityGuard.active ? velocityGuard.pct : undefined,
      minutes: velocityGuard.active ? velocityGuard.minutes : undefined,
    })
    await refresh()
  }
  const savePS = async () => {
    if (!validatePS({ trigger: ps.trigger, lock: ps.lock, stepProfit: ps.stepProfit, stepLock: ps.stepLock, ptInr: pt.inr })) return
    await postForm(`/baskets/${basket.id}/rm/profit-shield`, {
      active: ps.active ? '1' : '0',
      trigger: ps.active ? ps.trigger : undefined,
      lock: ps.active ? ps.lock : undefined,
      step_profit: ps.active ? ps.stepProfit : undefined,
      step_lock: ps.active ? ps.stepLock : undefined,
    })
    await refresh()
  }
  const toggleEod = async checked => {
    setEod(checked)
    await postForm(`/baskets/${basket.id}/rm/eod-exit`, { enabled: checked ? '1' : '0' })
    await refresh()
  }
  const toggleDof = async checked => {
    setDof(checked)
    await postForm(`/baskets/${basket.id}/rm/delete-on-fire`, { enabled: checked ? '1' : '0' })
    await refresh()
  }
  const rename = async () => {
    await postForm(`/baskets/${basket.id}/rename`, { name: name.trim() })
    await refresh()
  }
  const rearm = async () => {
    if (!window.confirm(`Re-arm ${basket.name}? This resets the fired flag, PS floor, and tick counters so the engine evaluates this basket fresh.`)) return
    await postForm(`/baskets/${basket.id}/rearm`, {})
    await refresh()
  }
  const delBasket = async () => {
    if (!window.confirm(`Delete ${basket.name}? Positions will move to Unallocated.`)) return
    await postForm(`/baskets/${basket.id}/delete`, {})
    await refresh()
  }

  return (
    <div>
      <div style={{ fontSize: 12.5, color: 'var(--muted)', letterSpacing: '.08em', textTransform: 'uppercase', fontWeight: 600, marginBottom: 10 }}>Risk Management</div>

      <RmTwoFieldCard title="Profit Target" toggleLabel="Enable Profit Target" f1Label="Target P&L (₹)" f1Placeholder="e.g. 15000"
        draft={pt} onChange={setPt} onSave={savePT} onCancel={() => setPt({ active: rm.pt_active, inr: rm.pt_inr, ticks: rm.pt_ticks })} />

      <RmTwoFieldCard title="Loss Guard" toggleLabel="Enable Loss Guard" f1Label="Max Loss (₹)" f1Placeholder="e.g. 10000"
        draft={lg} onChange={setLg} onSave={saveLG} onCancel={() => setLg({ active: rm.lg_active, inr: rm.lg_inr, ticks: rm.lg_ticks })} />

      {(() => {
        const underlying = detectUnderlying(basket.positions || [])
        return (
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '-4px 0 10px' }}>
            {underlying
              ? <>Spot guards below watch <b style={{ color: 'var(--text-2)' }}>{underlying}</b> spot.</>
              : 'Spot guards need index option legs to detect an underlying — not available for this basket.'}
          </p>
        )
      })()}

      <Card style={{ marginBottom: 10 }}>
        <div style={{ padding: '12px 15px', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 14.5 }}>Spot Range Guard</div>
        <div style={{ padding: 15, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Toggle checked={!!spotGuard.active} onChange={active => setSpotGuard({ ...spotGuard, active })} label="Enable Spot Range Guard" />
          <div style={{ display: 'flex', gap: 10 }}>
            <NumberField label="Lower Limit" placeholder="e.g. 23000" disabled={!spotGuard.active}
              value={spotGuard.lower} onChange={lower => setSpotGuard({ ...spotGuard, lower })} />
            <NumberField label="Upper Limit" placeholder="e.g. 23500" disabled={!spotGuard.active}
              value={spotGuard.upper} onChange={upper => setSpotGuard({ ...spotGuard, upper })} />
          </div>
          <NumberField label="Confirm Checks" hint="× 1 sec each" placeholder="e.g. 2-3" disabled={!spotGuard.active}
            value={spotGuard.ticks} onChange={ticks => setSpotGuard({ ...spotGuard, ticks })} />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button variant="ghost" onClick={() => setSpotGuard({ active: rm.spot_guard_active, lower: rm.spot_lower, upper: rm.spot_upper, ticks: rm.spot_guard_ticks })}>Cancel</Button>
            <Button variant="primary" onClick={saveSpotGuard}>Save</Button>
          </div>
        </div>
      </Card>

      <Card style={{ marginBottom: 10 }}>
        <div style={{ padding: '12px 15px', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 14.5 }}>Spot Velocity Guard</div>
        <div style={{ padding: 15, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Toggle checked={!!velocityGuard.active} onChange={active => setVelocityGuard({ ...velocityGuard, active })} label="Enable Spot Velocity Guard" />
          <div style={{ display: 'flex', gap: 10 }}>
            <NumberField label="% Change" placeholder="e.g. 1.5" disabled={!velocityGuard.active}
              value={velocityGuard.pct} onChange={pct => setVelocityGuard({ ...velocityGuard, pct })} />
            <NumberField label="Time Window (min)" placeholder="e.g. 15" disabled={!velocityGuard.active}
              value={velocityGuard.minutes} onChange={minutes => setVelocityGuard({ ...velocityGuard, minutes })} />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button variant="ghost" onClick={() => setVelocityGuard({ active: rm.velocity_guard_active, pct: rm.velocity_pct, minutes: rm.velocity_minutes })}>Cancel</Button>
            <Button variant="primary" onClick={saveVelocityGuard}>Save</Button>
          </div>
        </div>
      </Card>

      <Card style={{ marginBottom: 10 }}>
        <div style={{ padding: '12px 15px', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 14.5 }}>Profit Shield</div>
        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Toggle checked={!!ps.active} onChange={active => setPs({ ...ps, active })} label="Enable Profit Shield" />
          <div style={{ display: 'flex', gap: 10 }}>
            <NumberField label="If profit reaches (₹)" placeholder="e.g. 10000" disabled={!ps.active}
              value={ps.trigger} onChange={trigger => setPs({ ...ps, trigger })} />
            <NumberField label="Lock min profit at (₹)" placeholder="e.g. 7000" disabled={!ps.active}
              value={ps.lock} onChange={lock => setPs({ ...ps, lock })} />
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <NumberField label="Increase in profit (₹)" placeholder="Step size e.g. 2000" disabled={!ps.active}
              value={ps.stepProfit} onChange={stepProfit => setPs({ ...ps, stepProfit })} />
            <NumberField label="Increase min profit by (₹)" placeholder="Step lock e.g. 1500" disabled={!ps.active}
              value={ps.stepLock} onChange={stepLock => setPs({ ...ps, stepLock })} />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button variant="ghost" onClick={() => setPs({ active: rm.ps_active, trigger: rm.ps_trigger, lock: rm.ps_lock, stepProfit: rm.ps_step_profit, stepLock: rm.ps_step_lock })}>Cancel</Button>
            <Button variant="primary" onClick={savePS}>Save</Button>
          </div>
        </div>
      </Card>

      <Card style={{ marginBottom: 10, padding: 15 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 13 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>EOD Auto-Exit</div>
            <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>Exits all positions at 3:10 PM</div>
          </div>
          <Toggle checked={eod} onChange={toggleEod} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Delete Basket on Fire</div>
            <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>Removes basket automatically after exit</div>
          </div>
          <Toggle checked={dof} onChange={toggleDof} />
        </div>
      </Card>

      <Card style={{ marginBottom: 10, padding: 15, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>Basket Name</span>
          <input type="text" value={name} onChange={e => setName(e.target.value)}
            style={{ background: 'var(--panel-2)', border: '1px solid var(--line-2)', borderRadius: 6, color: 'var(--text)', padding: '8px 10px', fontSize: 14 }} />
        </label>
        <Button variant="ghost" onClick={rename}>Rename</Button>
      </Card>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <Button variant="ghost" onClick={rearm}>Re-arm RM</Button>
        <Button variant="danger" onClick={delBasket}>Delete Basket</Button>
      </div>
    </div>
  )
}
