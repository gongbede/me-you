import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { confirmEmailChange, confirmEmailVerification, requestEmailVerification } from '../api/auth'
import { VerifyEmailPage } from './VerifyEmailPage'

vi.mock('../api/auth', () => ({
  confirmEmailChange: vi.fn(),
  confirmEmailVerification: vi.fn(),
  requestEmailVerification: vi.fn(),
}))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => ({ user: null }) }))

describe('VerifyEmailPage', () => {
  afterEach(() => cleanup())

  it('confirms an email-change token through the email-change endpoint', async () => {
    vi.mocked(confirmEmailChange).mockResolvedValue({ message: 'Email address updated' })
    render(<MemoryRouter initialEntries={['/verify-email?token=01234567890123456789012345678901&action=email-change']}><VerifyEmailPage /></MemoryRouter>)

    fireEvent.click(screen.getByRole('button', { name: 'Confirm new email' }))

    await waitFor(() => expect(vi.mocked(confirmEmailChange).mock.calls[0]?.[0]).toEqual({
      token: '01234567890123456789012345678901',
    }))
    expect(await screen.findByText('Email address updated')).toBeInTheDocument()
    expect(confirmEmailVerification).not.toHaveBeenCalled()
    expect(requestEmailVerification).not.toHaveBeenCalled()
  })
})
