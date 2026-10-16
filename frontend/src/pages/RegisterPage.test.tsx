import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RegisterPage } from './RegisterPage'

const { register } = vi.hoisted(() => ({ register: vi.fn() }))

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ register, loginWithGoogle: vi.fn() }),
}))
vi.mock('../components/GoogleSignInButton', () => ({
  GoogleSignInButton: () => null,
}))

describe('RegisterPage', () => {
  afterEach(() => cleanup())

  it.each(['Ada Lovelace', ' Ada '])('rejects handle %j before calling registration', async (handle) => {
    register.mockReset()
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    )
    await user.type(screen.getByLabelText('Your name'), handle)
    await user.type(screen.getByLabelText('Email address'), 'ada@example.test')
    await user.type(screen.getByLabelText('Password'), 'long-enough-password')
    await user.type(screen.getByLabelText('Confirm password'), 'long-enough-password')
    fireEvent.submit(screen.getByRole('button', { name: 'Create account' }).closest('form')!)

    expect(screen.getByText('Your handle cannot contain whitespace.')).toBeInTheDocument()
    expect(screen.getByLabelText('Your name')).toHaveAttribute('aria-invalid', 'true')
    expect(register).not.toHaveBeenCalled()
  })
})
