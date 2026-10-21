import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import {
  followUser,
  getPublicProfile,
  getUserFollowersPage,
  getUserFollowingPage,
  getUserPosts,
  unfollowUser,
} from '../api/social'
import { listBlockedUsers } from '../api/moderation'
import { createDirectConversation } from '../api/messaging'
import { PublicProfilePage } from './PublicProfilePage'

vi.mock('../api/social', () => ({
  followUser: vi.fn(),
  getPublicProfile: vi.fn(),
  getUserFollowersPage: vi.fn(),
  getUserFollowingPage: vi.fn(),
  getUserPosts: vi.fn(),
  unfollowUser: vi.fn(),
}))
vi.mock('../api/moderation', () => ({
  blockUser: vi.fn(),
  listBlockedUsers: vi.fn(),
  unblockUser: vi.fn(),
}))
vi.mock('../api/messaging', () => ({ createDirectConversation: vi.fn() }))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'viewer-id', username: 'viewer', email: 'viewer@example.test' } }) }))

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/users/target-id']}>
        <Routes><Route path="/users/:userId" element={<PublicProfilePage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PublicProfilePage', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    vi.mocked(getPublicProfile).mockResolvedValue({
      user_id: 'target-id',
      display_name: 'Target learner',
      bio: 'Learning together',
      profile_picture_url: null,
      location: null,
      website: null,
      visibility: 'PUBLIC',
      username: 'target',
      joined_at: '2025-01-01T00:00:00Z',
      post_count: 1,
      reel_count: 1,
      follower_count: 3,
      following_count: 2,
      is_following: false,
    })
    vi.mocked(getUserPosts).mockImplementation(async (_userId, type) => ({
      items: [{
        id: `${type}-id`,
        author_id: 'target-id',
        author: { id: 'target-id', username: 'target', display_name: 'Target learner', avatar_url: null },
        content: `${type} item`,
        visibility: 'PUBLIC',
        post_type: type,
        media_asset_id: null,
        video_url: null,
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
        edited: false,
        attachments: [],
        like_count: 0,
        comment_count: 0,
        liked_by_me: false,
      }],
      offset: 0,
      limit: 20,
      has_more: false,
      next_cursor: null,
    }))
    vi.mocked(getUserFollowersPage).mockResolvedValue({
      items: [{ id: 'follower-id', username: 'follower' }], nextCursor: null,
    })
    vi.mocked(getUserFollowingPage).mockResolvedValue({
      items: [{ id: 'following-id', username: 'following' }], nextCursor: null,
    })
    vi.mocked(listBlockedUsers).mockResolvedValue([])
    vi.mocked(followUser).mockResolvedValue({ id: 'target-id', username: 'target' })
    vi.mocked(unfollowUser).mockResolvedValue(undefined)
    vi.mocked(createDirectConversation).mockResolvedValue({ id: 'conversation-id' } as never)
  })

  it('shows profile details and loads Posts, Reels, Followers, and Following tabs', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { level: 1, name: 'Target learner' })).toBeInTheDocument()
    expect(screen.getByText('@target · Joined 1/1/2025')).toBeInTheDocument()
    expect(await screen.findByText('POST item')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Reels' }))
    expect(await screen.findByText('REEL item')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Followers' }))
    expect(await screen.findByRole('link', { name: '@follower' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Following' }))
    expect(await screen.findByRole('link', { name: '@following' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Follow' }))
    await vi.waitFor(() => expect(vi.mocked(followUser).mock.calls[0]?.[0]).toBe('target-id'))
  })
})
