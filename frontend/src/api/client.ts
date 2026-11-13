// Small wrapper around fetch for the backend API (/api is proxied to FastAPI by Vite).

const TOKEN_KEY = 'case-search.token'

// sessionStorage, not localStorage: the login lasts for this browser tab only and is gone
// when the tab is closed, which matters on shared office computers.
export const tokenStore = {
  get: (): string | null => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  status: number
  /** The response body, e.g. the list of conflicts that came with a 409. */
  payload: unknown

  constructor(status: number, message: string, payload: unknown = null) {
    super(message)
    this.status = status
    this.payload = payload
  }
}

let onUnauthorized: () => void = () => {}

/** Called when the backend says the login is missing or expired (HTTP 401). */
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

type ParamValue = string | number | boolean | null | undefined | string[]

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE'
  json?: unknown
  body?: FormData | URLSearchParams
  params?: Record<string, ParamValue>
  /** Extra request headers, e.g. Idempotency-Key. */
  headers?: Record<string, string>
  /** For the login request itself: a 401 there means wrong credentials, not an expired login. */
  isLogin?: boolean
  /** Answer the file itself (a picture) instead of JSON. */
  as?: 'blob'
}

function errorMessage(payload: unknown, fallback: string): string {
  const detail = (payload as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc, msg, ...}]
    return detail.map((d: { msg?: string }) => d.msg ?? 'Invalid input').join('; ')
  }
  return fallback
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(`/api${path}`, window.location.origin)
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value === null || value === undefined || value === '') continue
    for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(key, String(item))
  }

  const headers: Record<string, string> = { ...options.headers }
  const token = tokenStore.get()
  if (token && !options.isLogin) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined = options.body
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.json)
  }

  let response: Response
  try {
    response = await fetch(url, { method: options.method ?? 'GET', headers, body })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the backend running?')
  }

  if (response.status === 401 && !options.isLogin) {
    tokenStore.clear()
    onUnauthorized()
    throw new ApiError(401, 'Your login has expired. Please log in again.')
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(response.status, errorMessage(payload, `Request failed (${response.status})`), payload)
  }
  if (response.status === 204) return undefined as T
  if (options.as === 'blob') return (await response.blob()) as T
  return (await response.json()) as T
}
