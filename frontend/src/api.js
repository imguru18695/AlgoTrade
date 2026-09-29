export async function fetchDashboard() {
  const r = await fetch('/api/dashboard')
  if (!r.ok) throw new Error(`dashboard ${r.status}`)
  return r.json()
}

export async function fetchManagement() {
  const r = await fetch('/api/management')
  if (!r.ok) throw new Error(`management ${r.status}`)
  return r.json()
}

export async function fetchLogs({ basketName = '', fromDate = '', toDate = '' } = {}) {
  const params = new URLSearchParams()
  if (basketName) params.set('basket_name', basketName)
  if (fromDate) params.set('from_date', fromDate)
  if (toDate) params.set('to_date', toDate)
  const r = await fetch('/api/logs?' + params.toString())
  if (!r.ok) throw new Error(`logs ${r.status}`)
  return r.json()
}

export async function fetchPnl() {
  const r = await fetch('/pnl')
  if (!r.ok) throw new Error(`pnl ${r.status}`)
  return r.json()
}

// Every /baskets/* route is Form(...)-based and 302-redirects back to
// /management on success. redirect:'manual' stops fetch from actually
// following that redirect and rendering/discarding the full Jinja page on
// every mutation — the caller re-fetches /api/management itself instead,
// so nothing is lost by not following it.
export async function postForm(url, fields = {}) {
  const fd = new FormData()
  for (const [k, v] of Object.entries(fields)) {
    if (v === undefined || v === null) continue
    if (Array.isArray(v)) v.forEach(item => fd.append(k, item))
    else fd.append(k, v)
  }
  const r = await fetch(url, { method: 'POST', body: fd, redirect: 'manual' })
  if (r.type !== 'opaqueredirect' && !r.ok) throw new Error(`${url} ${r.status}`)
}

export async function fetchSession() {
  // Not every backend serving this build has a login concept (e.g. demo.py) —
  // treat any failure as "unknown" rather than surface an error.
  try {
    const r = await fetch('/api/session')
    if (!r.ok) return null
    return await r.json()
  } catch {
    return null
  }
}
