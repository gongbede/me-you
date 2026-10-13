import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getNotificationsPage, getUnreadNotificationCount, markAllNotificationsRead, markNotificationRead } from '../api/notifications'
import { NotificationBell } from './NotificationBell'

vi.mock('../api/notifications', () => ({
  getNotificationsPage: vi.fn(),
  getUnreadNotificationCount: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}))

const unreadNotification = {
  id: 'notification-1',
  type: 'FOLLOW',
  title: 'New follower',
  payload: null,
  target_type: 'user',
  target_id: 'actor-1',
  actor: { id: 'actor-1', username: 'reader' },
  post_id: null,
  comment_id: null,
  created_at: '2026-10-12T12:00:00Z',
  read_at: null,
}

function renderBell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><NotificationBell /></MemoryRouter></QueryClientProvider>)
}

describe('NotificationBell', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    vi.mocked(getUnreadNotificationCount).mockResolvedValue({ unread_count: 3 })
    vi.mocked(getNotificationsPage).mockResolvedValue({ items: [unreadNotification], nextCursor: null })
    vi.mocked(markNotificationRead).mockResolvedValue({ ...unreadNotification, read_at: '2026-10-12T12:01:00Z' })
    vi.mocked(markAllNotificationsRead).mockResolvedValue({ updated: 3 })
  })

  it('shows the unread badge and marks one notification read', async () => {
    renderBell()
    fireEvent.click(await screen.findByRole('button', { name: 'Notifications, 3 unread' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Mark as read' }))

    await waitFor(() => expect(vi.mocked(markNotificationRead).mock.calls[0]?.[0]).toBe('notification-1'))
    expect(screen.getByText('reader started following you.')).toBeInTheDocument()
  })

  it('marks all notifications read from the panel', async () => {
    renderBell()
    fireEvent.click(await screen.findByRole('button', { name: 'Notifications, 3 unread' }))
    fireEvent.click(await screen.findByRole('button', { name: /mark all as read/i }))

    await waitFor(() => expect(vi.mocked(markAllNotificationsRead)).toHaveBeenCalledOnce())
  })
})