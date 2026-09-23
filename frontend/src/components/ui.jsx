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
