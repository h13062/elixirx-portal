const BASE_URL = import.meta.env.VITE_API_URL as string

async function handleResponse<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const message = data?.detail || data?.message || `Request failed (${res.status})`
    throw new Error(message)
  }
  return data as T
}

export async function apiPost<T = unknown>(endpoint: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

export async function apiGet<T = unknown>(endpoint: string, token?: string): Promise<T> {
  const headers: HeadersInit = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE_URL}${endpoint}`, { method: 'GET', headers })
  return handleResponse<T>(res)
}
