import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getNotificationsPage, getUnreadNotificationCount, markAllNotificationsRead, markNotificationRead } from '../api/notifications'
import { NotificationsPage } from './NotificationsPage'

vi.mock('../api/notifications', () => ({
  getNotificationsPage: vi.fn(),
  getUnreadNotificationCount: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}))

const notification = {
  id: 'notification-1',
  type: 'MESSAGE',
  title: 'New message',
  payload: null,
  target_type: 'conversation',
  target_id: 'conversation-1',
  actor: { id: 'actor-1', username: 'reader' },
  post_id: null,
  comment_id: null,
  created_at: '2026-10-12T12:00:00Z',
  read_at: null,
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><NotificationsPage /></MemoryRouter></QueryClientProvider>)
}

describe('NotificationsPage', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    vi.mocked(getUnreadNotificationCount).mockResolvedValue({ unread_count: 1 })
    vi.mocked(markNotificationRead).mockResolvedValue({ ...notification, read_at: '2026-10-12T12:01:00Z' })
    vi.mocked(markAllNotificationsRead).mockResolvedValue({ updated: 1 })
  })

  it('loads the next cursor page', async () => {
    vi.mocked(getNotificationsPage)
      .mockResolvedValueOnce({ items: [notification], nextCursor: 'next-page' })
      .mockResolvedValueOnce({ items: [{ ...notification, id: 'notification-2', read_at: '2026-10-12T12:01:00Z' }], nextCursor: null })
    renderPage()

    expect(await screen.findByText('reader sent you a message.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
    await waitFor(() => expect(screen.getAllByText('reader sent you a message.')).toHaveLength(2))
    expect(vi.mocked(getNotificationsPage)).toHaveBeenNthCalledWith(2, 'next-page')
  })

  it('shows the caught-up empty state', async () => {
    vi.mocked(getNotificationsPage).mockResolvedValueOnce({ items: [], nextCursor: null })
    renderPage()

    expect(await screen.findByText('You’re all caught up.')).toBeInTheDocument()
  })
})