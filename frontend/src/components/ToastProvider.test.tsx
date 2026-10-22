import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ToastProvider, useToast } from './ToastProvider'

function ToastProbe() {
  const toast = useToast()
  return <button type="button" onClick={() => toast('success', 'Your post was shared.')}>Post</button>
}

describe('ToastProvider', () => {
  afterEach(cleanup)

  it('announces success feedback and lets the user dismiss it', () => {
    render(<ToastProvider><ToastProbe /></ToastProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Post' }))
    expect(screen.getByRole('status')).toHaveTextContent('Your post was shared.')
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss message' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})