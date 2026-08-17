/**
 * Typed API Client.
 * Central HTTP client that attaches auth tokens to all requests.
 * Handles 401 responses by triggering logout.
 * 
 * SECURITY: Token stored in memory only (not localStorage/sessionStorage).
 * Lost on page reload — user must re-authenticate.
 */

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// In-memory token storage (not persisted to disk)
let _accessToken: string | null = null

export function setAccessToken(token: string | null) {
  _accessToken = token
}

export function getAccessToken(): string | null {
  return _accessToken
}

export function clearAccessToken() {
  _accessToken = null
}

// Logout callback (set by AuthProvider)
let _onUnauthorized: (() => void) | null = null

export function setOnUnauthorized(callback: () => void) {
  _onUnauthorized = callback
}

/**
 * Core fetch wrapper with auth and error handling.
 */
async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }

  // Attach auth token if available
  if (_accessToken) {
    headers['Authorization'] = `Bearer ${_accessToken}`
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  })

  // Handle 401 — token expired or invalid
  if (response.status === 401) {
    clearAccessToken()
    _onUnauthorized?.()
    throw new ApiError(401, 'Session expired. Please log in again.')
  }

  // Handle 429 — rate limited
  if (response.status === 429) {
    const data = await response.json().catch(() => ({}))
    throw new ApiError(429, data.detail || 'Rate limit exceeded. Please wait.')
  }

  // Handle other errors
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new ApiError(response.status, data.detail || `Error ${response.status}`)
  }

  // Parse JSON response
  if (response.status === 204) {
    return undefined as T
  }
  return response.json()
}

/**
 * Typed API error class.
 */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

// === Auth API ===

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  role: string
  display_name: string
  user_id: string
}

export interface UserInfo {
  user_id: string
  username: string
  email: string
  role: string
  display_name: string
  last_login?: string
  permissions?: Record<string, boolean>
}

export interface WSTicketResponse {
  ticket: string
  expires_in: number
}

export const authApi = {
  login: (username: string, password: string) =>
    apiFetch<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  me: () => apiFetch<UserInfo>('/api/auth/me'),

  logout: () => apiFetch<{ message: string }>('/api/auth/logout', { method: 'POST' }),

  getWsTicket: () => apiFetch<WSTicketResponse>('/api/auth/ws-ticket', { method: 'POST' }),

  changePassword: (currentPassword: string, newPassword: string) =>
    apiFetch<{ message: string }>('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
}

// === Dashboard API ===

export const dashboardApi = {
  getStats: () => apiFetch<Record<string, unknown>>('/api/dashboard/stats'),
  getRecentVisitors: () => apiFetch<Record<string, unknown>[]>('/api/dashboard/recent-visitors'),
  getSystemStatus: () => apiFetch<Record<string, unknown>>('/api/dashboard/system-status'),
}

// === Export the fetch utility for custom calls ===
export { apiFetch }
