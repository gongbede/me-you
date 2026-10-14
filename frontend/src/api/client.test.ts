import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest, clearCsrfToken, getFriendlyErrorMessage, setCsrfToken } from './client'

beforeEach(() => {
  clearCsrfToken()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCsrfToken()
})

describe('API error messages', () => {
  it('uses Retry-After to give a friendly 429 message', () => {
    const message = getFriendlyErrorMessage(
      new ApiError('Too many requests', 429, '17'),
    )
    expect(message).toBe('You’re moving quickly. Please try again in 17 seconds.')
  })

  it('uses a friendly fallback when Retry-After is not numeric', () => {
    const message = getFriendlyErrorMessage(new ApiError('Busy', 429, null))
    expect(message).toContain('try again in a little while')
  })

  it('sends cookie credentials and the in-memory CSRF token for state changes', async () => {
    setCsrfToken('session-bound-csrf-token')

    await apiRequest('/api/v1/messages/1', { method: 'PATCH', body: { content: 'Updated' } })

    const init = vi.mocked(fetch).mock.calls[0]?.[1]
    expect(init?.credentials).toBe('include')
    expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('session-bound-csrf-token')
    expect(new Headers(init?.headers).has('Authorization')).toBe(false)
  })

  it('omits cookies and CSRF headers from public requests', async () => {
    setCsrfToken('session-bound-csrf-token')

    await apiRequest('/api/v1/register', { method: 'POST', body: {}, auth: false })

    const init = vi.mocked(fetch).mock.calls[0]?.[1]
    expect(init?.credentials).toBe('omit')
    expect(new Headers(init?.headers).has('X-CSRF-Token')).toBe(false)
  })
})