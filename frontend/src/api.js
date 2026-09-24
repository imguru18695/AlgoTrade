export async function fetchDashboard() {
  const r = await fetch('/api/dashboard')
  if (!r.ok) throw new Error(`dashboard ${r.status}`)
  return r.json()
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
