export async function fetchDashboard() {
  const r = await fetch('/api/dashboard')
  if (!r.ok) throw new Error(`dashboard ${r.status}`)
  return r.json()
}
