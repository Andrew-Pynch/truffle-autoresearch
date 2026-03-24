const BASE = ''

async function request(path, { method = 'GET', token } = {}) {
  const headers = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, { method, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const checkHealth = () => request('/api/health')
export const getStatus = (token) => request('/api/status', { token })
export const getTrajectory = (machine, token) => request(`/api/results/${machine}/trajectory`, { token })
export const getLogs = (machine, token) => request(`/api/logs/${machine}`, { token })
export const startResearcher = (machine, token) => request(`/api/researcher/${machine}/start`, { method: 'POST', token })
export const stopResearcher = (machine, token) => request(`/api/researcher/${machine}/stop`, { method: 'POST', token })
export const syncResults = (machine, token) => request(`/api/sync/${machine}`, { method: 'POST', token })
export const runTruffile = (command, token) => request(`/api/truffile/${command}`, { method: 'POST', token })
