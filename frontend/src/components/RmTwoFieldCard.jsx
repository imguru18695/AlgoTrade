import { Card, Toggle, NumberField, Button } from './ui.jsx'

// Mirrors the old rm_2field_card Jinja macro — shared shape for Profit
// Target and Loss Guard, which both have exactly one primary INR field plus
// a "confirm ticks" field alongside the enable toggle.
export default function RmTwoFieldCard({
  title, f1Label, f1Placeholder, toggleLabel,
  draft, onChange, onSave, onCancel,
}) {
  return (
    <Card style={{ marginBottom: 10 }}>
      <div style={{ padding: '12px 15px', borderBottom: '1px solid var(--line)', fontWeight: 600, fontSize: 14.5 }}>{title}</div>
      <div style={{ padding: 15, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Toggle checked={!!draft.active} onChange={active => onChange({ ...draft, active })} label={toggleLabel} />
        <div style={{ display: 'flex', gap: 10 }}>
          <NumberField label={f1Label} placeholder={f1Placeholder} disabled={!draft.active}
            value={draft.inr} onChange={inr => onChange({ ...draft, inr })} />
          <NumberField label="Confirm Checks" hint="× 5 sec each" placeholder="e.g. 5 = holds for 25s" disabled={!draft.active}
            value={draft.ticks} onChange={ticks => onChange({ ...draft, ticks })} />
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button variant="primary" onClick={onSave}>Save</Button>
        </div>
      </div>
    </Card>
  )
}
