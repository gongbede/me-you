import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { getPlatformAdminAccess, listAdminReports } from '../api/moderation'
import { AdminReportsPage } from './AdminReportsPage'

vi.mock('../api/moderation', () => ({
  getPlatformAdminAccess: vi.fn(),
  listAdminReports: vi.fn(),
  setAdminContentHidden: vi.fn(),
  suspendUser: vi.fn(),
  unsuspendUser: vi.fn(),
  updateAdminReport: vi.fn(),
}))

describe('AdminReportsPage', () => {
  it('denies access and does not request the reports queue for a non-admin', async () => {
    vi.mocked(getPlatformAdminAccess).mockResolvedValue({ is_platform_admin: false })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><AdminReportsPage /></QueryClientProvider>)

    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument()
    expect(listAdminReports).not.toHaveBeenCalled()
  })
})
