import { supabase } from './supabaseClient'

const BASE_URL = import.meta.env.VITE_API_URL as string

/**
 * Single source of truth for "what should we do when auth is unrecoverable" —
 * registered by AuthProvider on mount so api.ts can redirect to /login without
 * importing react-router here.
 */
let onAuthFailure: () => void = () => {
  /* no-op until AuthProvider registers */
}

export function registerAuthFailureHandler(handler: () => void): void {
  onAuthFailure = handler
}

async function handleResponse<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const message = data?.detail || data?.message || `Request failed (${res.status})`
    throw new Error(message)
  }
  return data as T
}

async function getCurrentToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

/**
 * Authenticated fetch wrapper.
 *
 * - Reads the current access_token from the supabase session (which is also
 *   auto-refreshed in the background).
 * - On a 401 response, calls `supabase.auth.refreshSession()` once and retries
 *   the original request with the new token.
 * - If refresh fails (no refresh_token, or refresh_token rejected), invokes
 *   the registered auth-failure handler — typically a redirect to /login.
 */
async function fetchWithAuth(input: string, init: RequestInit = {}): Promise<Response> {
  const token = await getCurrentToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let res = await fetch(input, { ...init, headers })

  if (res.status === 401) {
    const { data: refreshed, error } = await supabase.auth.refreshSession()
    const newToken = refreshed?.session?.access_token
    if (error || !newToken) {
      onAuthFailure()
      // Surface a clear error to callers so they don't render stale data.
      throw new Error('Session expired')
    }
    headers.set('Authorization', `Bearer ${newToken}`)
    res = await fetch(input, { ...init, headers })
  }

  return res
}

// ─── Unauthenticated POST (login, admin-setup) ──────────────────────────

export async function apiPost<T = unknown>(endpoint: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

// ─── Authenticated helpers (token resolved from supabase session) ───────
// The optional `_legacyToken` parameter is ignored — kept so existing call
// sites (apiGet('/foo', access_token)) compile without churn.

export async function apiGet<T = unknown>(endpoint: string, _legacyToken?: string): Promise<T> {
  const res = await fetchWithAuth(`${BASE_URL}${endpoint}`, { method: 'GET' })
  return handleResponse<T>(res)
}

/**
 * GET a resource that may legitimately not exist.
 *
 * Returns `null` on 404 (e.g., "no warranty for this machine yet"). Throws on
 * any other non-OK status so a 500 doesn't get silently swallowed and rendered
 * as "no data".
 */
export async function apiGetOptional<T = unknown>(
  endpoint: string,
  _legacyToken?: string,
): Promise<T | null> {
  const res = await fetchWithAuth(`${BASE_URL}${endpoint}`, { method: 'GET' })
  if (res.status === 404) return null
  return handleResponse<T>(res)
}

export async function apiPut<T = unknown>(
  endpoint: string,
  body: unknown,
  _legacyToken?: string,
): Promise<T> {
  const res = await fetchWithAuth(`${BASE_URL}${endpoint}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

export async function apiPostAuth<T = unknown>(
  endpoint: string,
  body: unknown,
  _legacyToken?: string,
): Promise<T> {
  const res = await fetchWithAuth(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

export async function apiDelete<T = unknown>(
  endpoint: string,
  _legacyToken?: string,
): Promise<T> {
  const res = await fetchWithAuth(`${BASE_URL}${endpoint}`, { method: 'DELETE' })
  return handleResponse<T>(res)
}

/** Fetch a binary blob (e.g. PDF download). Throws on non-OK status. */
export async function apiGetBlob(endpoint: string, _legacyToken?: string): Promise<Blob> {
  const res = await fetchWithAuth(`${BASE_URL}${endpoint}`, { method: 'GET' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data?.detail || data?.message || `Request failed (${res.status})`)
  }
  return res.blob()
}
