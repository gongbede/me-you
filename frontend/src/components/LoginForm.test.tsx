import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { LoginForm } from './LoginForm'

describe('LoginForm', () => {
  it('requires a valid email and password before submitting', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<LoginForm onSubmit={onSubmit} error={null} loading={false} />)

    const email = screen.getByRole('textbox', { name: 'Email address' })
    const password = screen.getByLabelText('Password')
    expect(email).toBeRequired()
    expect(password).toBeRequired()
    expect(password).toHaveAttribute('minlength', '8')

    await user.type(email, 'not-an-email')
    await user.type(password, 'short')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(email).not.toBeValid()
    expect(password).toHaveAttribute('minlength', '8')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('displays backend errors accessibly', () => {
    render(<LoginForm onSubmit={vi.fn()} error="Invalid email or password" loading={false} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid email or password')
  })
})