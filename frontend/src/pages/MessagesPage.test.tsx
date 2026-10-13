import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createDirectConversation,
  getConversation,
  listConversationMessages,
  listConversations,
  markConversationRead,
  sendConversationMessage,
} from '../api/messaging'
import { getPublicProfile, getUserFollowers, followUser, unfollowUser } from '../api/social'
import { PublicProfilePage } from './PublicProfilePage'
import { MessagesPage } from './MessagesPage'

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'viewer-id', username: 'viewer', email: 'viewer@example.test' } }),
}))

vi.mock('../api/messaging', () => ({
  createDirectConversation: vi.fn(),
  createGroupConversation: vi.fn(),
  deleteMessage: vi.fn(),
  editMessage: vi.fn(),
  getConversation: vi.fn(),
  listConversationMessages: vi.fn(),
  listConversations: vi.fn(),
  markConversationRead: vi.fn(),
  sendConversationMessage: vi.fn(),
}))

vi.mock('../api/social', () => ({
  followUser: vi.fn(),
  getPublicProfile: vi.fn(),
  getUserFollowers: vi.fn(),
  getUserFollowing: vi.fn(),
  unfollowUser: vi.fn(),
}))

const conversation = {
  id: 'conversation-1',
  type: 'DIRECT' as const,
  name: null,
  description: null,
  created_at: '2026-10-12T12:00:00Z',
  updated_at: '2026-10-12T12:00:00Z',
  members: [
    { user: { id: 'viewer-id', username: 'viewer' }, joined_at: '2026-10-12T12:00:00Z', last_read_at: null },
    { user: { id: 'other-id', username: 'other' }, joined_at: '2026-10-12T12:00:00Z', last_read_at: null },
  ],
  last_message_preview: null,
  last_message_at: null,
  unread_count: 0,
}

const incomingMessage = {
  id: 'message-incoming',
  conversation_id: conversation.id,
  sender: { id: 'other-id', username: 'other' },
  content: 'Incoming while open',
  created_at: '2026-10-12T12:01:00Z',
  updated_at: '2026-10-12T12:01:00Z',
  deleted_at: null,
}

function renderMessages(path = '/messages/conversation-1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/messages" element={<MessagesPage />} />
          <Route path="/messages/:conversationId" element={<MessagesPage />} />
          <Route path="/users/:userId" element={<PublicProfilePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MessagesPage', () => {
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  beforeEach(() => {
    vi.mocked(listConversations).mockResolvedValue([conversation])
    vi.mocked(getConversation).mockResolvedValue(conversation)
    vi.mocked(listConversationMessages).mockResolvedValue({ items: [], nextCursor: null })
    vi.mocked(markConversationRead).mockResolvedValue({ conversation_id: conversation.id, last_read_at: '2026-10-12T12:00:00Z', unread_count: 0 })
    vi.mocked(sendConversationMessage).mockResolvedValue({
      id: 'message-sent', conversation_id: conversation.id,
      sender: { id: 'viewer-id', username: 'viewer' }, content: 'Hello',
      created_at: '2026-10-12T12:02:00Z', updated_at: '2026-10-12T12:02:00Z', deleted_at: null,
    })
    vi.mocked(getPublicProfile).mockResolvedValue({
      id: 'other-id', username: 'other', display_name: 'Other person', bio: null,
      location: null, website: null, profile_picture_url: null, visibility: 'PUBLIC',
    } as never)
    vi.mocked(getUserFollowers).mockResolvedValue([])
    vi.mocked(followUser).mockResolvedValue({ id: 'other-id', username: 'other' })
    vi.mocked(unfollowUser).mockResolvedValue()
    vi.mocked(createDirectConversation).mockResolvedValue(conversation)
  })

  it('shows an empty conversations state', async () => {
    vi.mocked(listConversations).mockResolvedValueOnce([])
    renderMessages('/messages')

    expect(await screen.findByText('No conversations yet.')).toBeInTheDocument()
  })

  it('sends optimistically, shows failure, and retries a failed message', async () => {
    vi.mocked(sendConversationMessage)
      .mockRejectedValueOnce(new Error('Network unavailable'))
      .mockResolvedValueOnce({
        id: 'message-retried', conversation_id: conversation.id,
        sender: { id: 'viewer-id', username: 'viewer' }, content: 'Hello',
        created_at: '2026-10-12T12:02:00Z', updated_at: '2026-10-12T12:02:00Z', deleted_at: null,
      })
    renderMessages()
    const composer = await screen.findByLabelText('Write a message')
    fireEvent.change(composer, { target: { value: 'Hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    expect(await screen.findByText('Not sent')).toBeInTheDocument()
    expect(screen.getByText('Hello')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(vi.mocked(sendConversationMessage)).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('Sent')).toBeInTheDocument()
  })

  it('polls for new messages while a conversation is open', async () => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    vi.mocked(listConversationMessages)
      .mockResolvedValueOnce({ items: [], nextCursor: null })
      .mockResolvedValue({ items: [incomingMessage], nextCursor: null })
    renderMessages()
    expect(screen.queryByText('Incoming while open')).not.toBeInTheDocument()
    expect(await screen.findByText('Incoming while open', {}, { timeout: 7_000 })).toBeInTheDocument()
  }, 10_000)

  it('creates or reuses a direct chat from a public profile', async () => {
    renderMessages('/users/other-id')
    fireEvent.click(await screen.findByRole('button', { name: 'Message' }))

    await waitFor(() => expect(vi.mocked(createDirectConversation)).toHaveBeenCalledWith('other-id'))
    expect(await screen.findByText('No messages yet. Say hello.')).toBeInTheDocument()
  })
})