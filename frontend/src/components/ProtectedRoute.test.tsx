import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProtectedRoute } from './ProtectedRoute'
import { AuthProvider } from '../hooks/useAuth'

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Not authenticated' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('redirects an anonymous visitor to login', async () => {
    render(
      <MemoryRouter initialEntries={['/private']}>
        <AuthProvider>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/private" element={<div>Private content</div>} />
            </Route>
            <Route path="/login" element={<div>Login destination</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Login destination')).toBeInTheDocument()
    expect(screen.queryByText('Private content')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/v1/account/session', expect.objectContaining({ credentials: 'include' }))
  })
})