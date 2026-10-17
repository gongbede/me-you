import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { submitReport } from '../api/moderation'
import { ReportDialog } from './ReportDialog'

vi.mock('../api/moderation', () => ({ submitReport: vi.fn() }))

describe('ReportDialog', () => {
  beforeEach(() => vi.mocked(submitReport).mockResolvedValue({
    id: 'report-id',
    target_type: 'POST',
    target_id: 'post-id',
    reason: 'SPAM',
    details: null,
    status: 'OPEN',
    created_at: '2026-01-01T00:00:00Z',
  }))

  it('opens only when invoked and confirms after submitting a report', async () => {
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><ReportDialog targetType="POST" targetId="post-id" /></QueryClientProvider>)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /report/i }))
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'HARASSMENT' } })
    fireEvent.change(screen.getByLabelText('Additional details (optional)'), { target: { value: 'Please review this.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Thank you')
    expect(submitReport).toHaveBeenCalledWith({
      target_type: 'POST',
      target_id: 'post-id',
      reason: 'HARASSMENT',
      details: 'Please review this.',
    })
  })
})
