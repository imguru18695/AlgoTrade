export const n0 = v => Math.round(v).toLocaleString('en-IN')
export const n2 = v => Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const pct = v => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2) + '%'
export const upc = v => (v >= 0 ? 'var(--up)' : 'var(--down)')
export const stateColor = s =>
  /Bull|Rising|Accum|Strong Buy|Buy|Strong$|Support/.test(s) ? 'var(--up)'
    : /Bear|Fall|Distrib|Sell|Weak|Oversold|Overbought|Resistance/.test(s) ? 'var(--down)'
    : 'var(--amber)'
export const cr = v => (v >= 0 ? '+' : '−') + '₹' + Math.abs(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Cr'
const _MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
// Formats a "YYYY-MM-DD" string by splitting it directly rather than going
// through `new Date(iso)` — that parses as UTC midnight, and converting back
// to the viewer's local time zone can silently shift the day by one.
export const fmtDate = iso => {
  if (!iso) return null
  const [, m, d] = iso.split('-')
  return `${d} ${_MONTHS[Number(m) - 1]}`
}
export function lastSessions(n) {
  const out = []; const d = new Date()
  while (out.length < n) {
    d.setDate(d.getDate() - 1)
    if (d.getDay() !== 0 && d.getDay() !== 6) out.push(d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }))
  }
  return out
}
