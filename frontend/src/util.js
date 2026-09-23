export const n0 = v => Math.round(v).toLocaleString('en-IN')
export const n2 = v => Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const pct = v => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2) + '%'
export const upc = v => (v >= 0 ? 'var(--up)' : 'var(--down)')
export const stateColor = s =>
  /Bull|Rising|Accum|Strong Buy|Buy|Strong$|Support/.test(s) ? 'var(--up)'
    : /Bear|Fall|Distrib|Sell|Weak|Oversold|Overbought|Resistance/.test(s) ? 'var(--down)'
    : 'var(--amber)'
export const cr = v => (v >= 0 ? '+' : '−') + '₹' + Math.abs(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Cr'
export function lastSessions(n) {
  const out = []; const d = new Date()
  while (out.length < n) {
    d.setDate(d.getDate() - 1)
    if (d.getDay() !== 0 && d.getDay() !== 6) out.push(d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }))
  }
  return out
}
