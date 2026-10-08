import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from '../api/client'
import { GoogleSignInButton } from './GoogleSignInButton'

vi.mock('../api/client', () => ({ apiRequest: vi.fn() }))

const request = vi.mocked(apiRequest)

describe('GoogleSignInButton', () => {
  beforeEach(() => {
    request.mockReset()
    delete window.google
  })

  afterEach(() => {
    delete window.google
  })

  it('stays hidden when Google sign-in is not configured', async () => {
    request.mockRejectedValue(new Error('Google sign-in is not configured'))
    const { container } = render(<GoogleSignInButton onSignIn={vi.fn()} />)
    await waitFor(() => expect(request).toHaveBeenCalled())
    expect(container.firstChild).toBeNull()
  })

  it('renders GIS and passes its credential to the sign-in handler', async () => {
    request.mockResolvedValue({ client_id: 'test-client-id' })
    const onSignIn = vi.fn().mockResolvedValue(undefined)
    let credentialCallback: ((response: { credential: string }) => void) | undefined
    const initialize = vi.fn((options: { callback: (response: { credential: string }) => void }) => {
      credentialCallback = options.callback
    })
    const renderButton = vi.fn()
    window.google = { accounts: { id: { initialize, renderButton } } }

    render(<GoogleSignInButton onSignIn={onSignIn} />)
    await waitFor(() => expect(initialize).toHaveBeenCalled())
    expect(screen.getByRole('group', { name: 'Continue with Google' })).toBeTruthy()
    expect(renderButton).toHaveBeenCalled()

    await act(async () => {
      credentialCallback?.({ credential: 'google-id-token' })
    })
    expect(onSignIn).toHaveBeenCalledWith('google-id-token')
  })
})