import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { login } from './auth'
import { apiRequest, clearCsrfToken } from './client'

beforeEach(() => {
  clearCsrfToken()
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({
      message: 'Login successful',
      id: 'user-1',
      username: 'learner',
      email: 'learner@example.test',
      csrf_token: 'session-bound-csrf-token',
    }), { headers: { 'Content-Type': 'application/json' } }))
    .mockResolvedValueOnce(new Response('{}')))
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCsrfToken()
})

describe('cookie-based authentication', () => {
  it('establishes an HttpOnly-cookie session and uses its CSRF token on later writes', async () => {
    await login({ email: 'learner@example.test', password: 'correct-password' })
    await apiRequest('/api/v1/account/logout', { method: 'POST' })

    const requests = vi.mocked(fetch).mock.calls
    const loginInit = requests[0]?.[1]
    const logoutInit = requests[1]?.[1]
    expect(loginInit?.credentials).toBe('include')
    expect(new Headers(loginInit?.headers).get('X-Me-You-Session')).toBe('cookie')
    expect(new Headers(loginInit?.headers).has('Authorization')).toBe(false)
    expect(logoutInit?.credentials).toBe('include')
    expect(new Headers(logoutInit?.headers).get('X-CSRF-Token')).toBe('session-bound-csrf-token')
  })
})