import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getUnreadNotificationCount } from '../api/notifications'
import { NotificationBell } from './NotificationBell'

vi.mock('../api/notifications', () => ({
  getUnreadNotificationCount: vi.fn(),
}))

function renderBell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><NotificationBell /></MemoryRouter></QueryClientProvider>)
}

describe('NotificationBell', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    vi.mocked(getUnreadNotificationCount).mockResolvedValue({ unread_count: 3 })
  })

  it('shows the unread badge and links directly to Notifications', async () => {
    renderBell()
    const link = await screen.findByRole('link', { name: 'Notifications, 3 unread' })
    expect(link).toHaveAttribute('href', '/notifications')
  })
})