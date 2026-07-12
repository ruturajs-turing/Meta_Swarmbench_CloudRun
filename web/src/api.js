const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:18080'
let token = localStorage.getItem('aegisrun_token')

async function request(path, options = {}) {
  const headers = { Accept: 'application/json', ...(options.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch(`${API_URL}${path}`, { ...options, headers })
  const text = await response.text()
  let body = {}
  if (text) {
    try { body = JSON.parse(text) } catch { body = { detail: text } }
  }
  if (!response.ok) {
    const error = new Error(body.detail || `Request failed (${response.status})`)
    error.status = response.status
    error.body = body
    throw error
  }
  return body
}

function query(path, params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '' && value !== 'ALL') search.set(key, value)
  })
  return request(`${path}${search.size ? `?${search}` : ''}`)
}

export const api = {
  url: API_URL,
  hasToken: () => Boolean(token),
  setToken(value) {
    token = value
    localStorage.setItem('aegisrun_token', value)
  },
  clearToken() {
    token = null
    localStorage.removeItem('aegisrun_token')
  },
  login(identifier, password) {
    return request('/v1/sessions', { method: 'POST', body: JSON.stringify({ identifier, password }) })
  },
  logout: () => request('/v1/sessions/current', { method: 'DELETE' }),
  me: () => request('/v1/me'),
  terminal: () => request('/v1/terminal'),
  overview: () => request('/admin/overview'),
  users: (params) => query('/admin/users', params),
  createUser: (body) => request('/admin/users', { method: 'POST', body: JSON.stringify(body) }),
  patchUser: (id, body) => request(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  resetPassword: (id, password) => request(`/admin/users/${id}/reset-password`, { method: 'POST', body: JSON.stringify({ password }) }),
  updateQuota: (id, body) => request(`/admin/users/${id}/quota`, { method: 'PATCH', body: JSON.stringify(body) }),
  parents: (params) => query('/admin/parents', params),
  createParent: (userId) => request('/admin/parents', { method: 'POST', body: JSON.stringify({ user_id: userId }) }),
  parentAction: (id, action) => request(`/admin/parents/${id}/${action}`, { method: 'POST' }),
  parentStats: (id) => request(`/admin/parents/${id}/stats`),
  runs: (params) => query('/admin/runs', params),
  run: (id) => request(`/v1/runs/${id}`),
  events: (id) => request(`/v1/runs/${id}/events`),
  artifacts: (id) => request(`/v1/runs/${id}/artifacts`),
  cancelRun: (id) => request(`/v1/runs/${id}/cancel`, { method: 'POST' }),
  retryRun: (id) => request(`/v1/runs/${id}/retry`, { method: 'POST' }),
  forceCleanup: (id) => request(`/admin/runs/${id}/force-cleanup`, { method: 'POST' }),
  providers: () => request('/admin/providers'),
  audit: (params) => query('/admin/audit', params),
  costs: () => request('/admin/costs'),
  reconcile: () => request('/admin/cleanup/reconcile', { method: 'POST' }),
  async downloadArtifact(runId, artifactId, filename) {
    const response = await fetch(`${API_URL}/v1/runs/${runId}/artifacts/${artifactId}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) throw new Error(`Download failed (${response.status})`)
    const blob = await response.blob()
    const href = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = href
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(href)
  },
}
