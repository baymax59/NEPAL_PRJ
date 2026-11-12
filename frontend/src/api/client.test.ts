import { describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, setUnauthorizedHandler, tokenStore } from './client'

function respond(status: number, body?: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('apiFetch', () => {
  it('sends the login token and repeats list parameters', async () => {
    tokenStore.set('abc')
    const fetchMock = respond(200, { ok: true })

    await apiFetch('/cases', { params: { outcome: ['Dismissed', 'Appeal(s) allowed'], year_from: 2023, year_to: null } })

    const [url, init] = fetchMock.mock.calls[0] as [URL, RequestInit]
    expect(url.pathname).toBe('/api/cases')
    expect(url.searchParams.getAll('outcome')).toEqual(['Dismissed', 'Appeal(s) allowed'])
    expect(url.searchParams.get('year_from')).toBe('2023')
    expect(url.searchParams.has('year_to')).toBe(false)
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer abc')
  })

  it('treats 401 as an expired login: forgets the token and tells the app', async () => {
    tokenStore.set('expired')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    respond(401, { detail: 'Not authenticated' })

    await expect(apiFetch('/cases')).rejects.toMatchObject({ status: 401 })
    expect(tokenStore.get()).toBeNull()
    expect(handler).toHaveBeenCalledOnce()
  })

  it('does not treat a failed login as an expired one', async () => {
    tokenStore.set('keep')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    respond(401, { detail: 'Incorrect username or password' })

    await expect(apiFetch('/auth/token', { method: 'POST', isLogin: true })).rejects.toThrow('Incorrect username or password')
    expect(handler).not.toHaveBeenCalled()
  })

  it('turns validation errors into a readable message', async () => {
    respond(422, { detail: [{ msg: 'year_from must not be after year_to' }, { msg: 'Field required' }] })

    const error = await apiFetch('/cases').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).message).toBe('year_from must not be after year_to; Field required')
  })

  it('reports an unreachable server clearly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(apiFetch('/cases')).rejects.toThrow('Cannot reach the server')
  })
})
