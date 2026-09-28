export const Card = ({ children, style }) => (
  <section className="card fadein" style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden', flexShrink: 0, ...style }}>
    {children}
  </section>
)

export const CardHead = ({ title, sub, right }) => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '13px 18px', borderBottom: '1px solid var(--line)' }}>
    <span style={{ fontWeight: 600, fontSize: 13.5 }}>{title}{sub && <span style={{ color: 'var(--muted)', fontWeight: 400, marginLeft: 8, fontSize: 11.5 }}>{sub}</span>}</span>
    {right}
  </div>
)

export const Tag = ({ children, color }) => (
  <span style={{ fontSize: 10.5, fontWeight: 600, color, background: 'color-mix(in srgb,' + color + ' 12%,transparent)', padding: '2px 8px', borderRadius: 4, whiteSpace: 'nowrap', lineHeight: 1.5 }}>{children}</span>
)

export function Row({ label, value, valueColor, tag, tagColor }) {
  return (
    <div className="row">
      <span className="row-k">{label}</span>
      <span className="row-v">
        {value != null && value !== '' && <span className="mono" style={{ fontWeight: 600, color: valueColor || 'var(--text)' }}>{value}</span>}
        {tag && <Tag color={tagColor}>{tag}</Tag>}
      </span>
    </div>
  )
}

export const Toggle = ({ checked, onChange, label, disabled }) => {
  const fire = () => !disabled && onChange?.(!checked)
  return (
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 9, cursor: disabled ? 'default' : 'pointer', opacity: disabled ? .5 : 1 }}>
      <span role="switch" aria-checked={!!checked} aria-label={label || undefined}
        tabIndex={disabled ? -1 : 0} onClick={fire}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fire() } }}
        style={{ position: 'relative', width: 34, height: 19, borderRadius: 10, flexShrink: 0,
          background: checked ? 'var(--teal)' : 'var(--panel-2)', border: '1px solid ' + (checked ? 'var(--teal)' : 'var(--line-2)'),
          transition: 'background .15s, border-color .15s' }}>
        <span style={{ position: 'absolute', top: 2, left: checked ? 16 : 2, width: 14, height: 14, borderRadius: '50%',
          background: checked ? '#04231f' : 'var(--muted)', transition: 'left .15s' }} />
      </span>
      {label && <span style={{ fontSize: 12.5, color: 'var(--text-2)' }}>{label}</span>}
    </label>
  )
}

export const NumberField = ({ label, hint, value, onChange, placeholder, disabled }) => (
  <label style={{ display: 'flex', flexDirection: 'column', gap: 5, flex: 1, minWidth: 0 }}>
    <span style={{ fontSize: 11, color: 'var(--muted)' }}>{label}{hint && <span style={{ color: 'var(--muted-2)', marginLeft: 5 }}>{hint}</span>}</span>
    <input type="number" min="1" step="1" value={value ?? ''} placeholder={placeholder} disabled={disabled}
      onChange={e => onChange?.(e.target.value === '' ? null : Number(e.target.value))}
      className="mono"
      style={{ background: 'var(--panel-2)', border: '1px solid var(--line-2)', borderRadius: 6, color: 'var(--text)',
        padding: '7px 9px', fontSize: 12.5, width: '100%', opacity: disabled ? .45 : 1 }} />
  </label>
)

export const Button = ({ children, onClick, variant = 'ghost', type = 'button', style }) => {
  const variants = {
    primary: { background: 'var(--teal)', color: '#04231f', border: '1px solid var(--teal)' },
    ghost:   { background: 'transparent', color: 'var(--text-2)', border: '1px solid var(--line-2)' },
    danger:  { background: 'transparent', color: 'var(--down)', border: '1px solid var(--line-2)' },
  }
  return (
    <button type={type} onClick={onClick}
      style={{ ...variants[variant], borderRadius: 7, padding: '7px 13px', fontSize: 12, fontWeight: 600, cursor: 'pointer', ...style }}>
      {children}
    </button>
  )
}
