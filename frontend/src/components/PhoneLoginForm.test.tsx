import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PhoneLoginForm } from './PhoneLoginForm'

describe('PhoneLoginForm', () => {
  it('requests a code, starts the resend countdown, and verifies the entered code', async () => {
    const user = userEvent.setup()
    const onRequestCode = vi.fn().mockResolvedValue(true)
    const onVerify = vi.fn().mockResolvedValue(undefined)
    render(
      <PhoneLoginForm
        error={null}
        loading={false}
        onRequestCode={onRequestCode}
        onVerify={onVerify}
      />,
    )

    await user.type(screen.getByRole('textbox', { name: 'Phone number' }), '+1 202 555 0111')
    await user.click(screen.getByRole('button', { name: 'Send code' }))

    expect(onRequestCode).toHaveBeenCalledWith('+1 202 555 0111')
    expect(await screen.findByRole('status')).toHaveTextContent('a sign-in code has been sent')
    expect(screen.getByRole('button', { name: /Resend code in \d+s/ })).toBeDisabled()

    await user.type(screen.getByRole('textbox', { name: '6-digit code' }), '123456')
    await user.click(screen.getByRole('button', { name: 'Verify and sign in' }))
    expect(onVerify).toHaveBeenCalledWith('+1 202 555 0111', '123456')
  })

  it('shows backend phone errors accessibly', () => {
    render(
      <PhoneLoginForm
        error="Invalid or expired phone sign-in code"
        loading={false}
        onRequestCode={vi.fn()}
        onVerify={vi.fn()}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid or expired phone sign-in code')
  })
})