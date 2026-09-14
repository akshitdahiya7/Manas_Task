// One place for HTTP: attaches the token, and turns the backend's error
// envelope into an ApiError so every page can render failures the same way.

const TOKEN_KEY = 'manas.token'
const USER_KEY = 'manas.user'

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message)
    this.status = status
    this.code = code
    this.details = details || []
  }

  // Validation errors arrive as [{field, message, type}]; group them by field
  // so a form can show each message next to its input.
  get fieldErrors() {
    const map = {}
    for (const detail of this.details) {
      if (detail.field) map[detail.field] = detail.message
    }
    return map
  }
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

async function request(path, { method = 'GET', body, isFormData = false } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (!isFormData && body !== undefined) headers['Content-Type'] = 'application/json'

  let response
  try {
    response = await fetch(path, {
      method,
      headers,
      body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'network_error', 'Could not reach the server. Is the backend running?')
  }

  if (response.status === 401) {
    // The token is gone or expired - drop it so the app returns to login.
    clearSession()
  }

  const text = await response.text()
  const payload = text ? safeJson(text) : null

  if (!response.ok) {
    const error = payload && payload.error
    throw new ApiError(
      response.status,
      error?.code || 'http_error',
      error?.message || `Request failed with status ${response.status}`,
      error?.details,
    )
  }

  return payload
}

function safeJson(text) {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export const api = {
  login: (username, password) =>
    request('/api/auth/login', { method: 'POST', body: { username, password } }),
  me: () => request('/api/auth/me'),

  predict: (record, version) =>
    request(`/api/predict${version ? `?version=${encodeURIComponent(version)}` : ''}`, {
      method: 'POST',
      body: record,
    }),

  predictBatch: (records, version) =>
    request(`/api/predict/batch${version ? `?version=${encodeURIComponent(version)}` : ''}`, {
      method: 'POST',
      body: { records },
    }),

  predictCsv: (file, version) => {
    const form = new FormData()
    form.append('file', file)
    return request(`/api/predict/csv${version ? `?version=${encodeURIComponent(version)}` : ''}`, {
      method: 'POST',
      body: form,
      isFormData: true,
    })
  },

  models: () => request('/api/models'),
  activeModel: () => request('/api/models/active'),
  promote: (version, reason) =>
    request(`/api/models/${encodeURIComponent(version)}/promote`, {
      method: 'POST',
      body: { reason },
    }),
  rollback: (reason) => request('/api/models/rollback', { method: 'POST', body: { reason } }),
  promotions: () => request('/api/models/promotions'),

  logs: (params = {}) => request(`/api/logs?${new URLSearchParams(params)}`),
  batches: (params = {}) => request(`/api/batches?${new URLSearchParams(params)}`),
  batch: (id) => request(`/api/batches/${id}`),

  metrics: () => request('/api/metrics/summary'),
}
