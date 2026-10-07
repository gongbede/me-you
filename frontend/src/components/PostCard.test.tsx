import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getPostEngagement, setPostLike } from '../api/social'
import { PostCard } from './PostCard'

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'viewer-id', username: 'viewer', email: 'viewer@example.test' } }),
}))

vi.mock('../api/social', () => ({
  deletePost: vi.fn(),
  getPostEngagement: vi.fn(),
  setPostLike: vi.fn(),
}))

vi.mock('./UserIdentity', () => ({
  UserIdentity: ({ username }: { username: string }) => <span>{username}</span>,
}))

vi.mock('./CommentsSection', () => ({
  CommentsSection: () => <div>Comments panel</div>,
  relativeTime: () => 'just now',
}))

const post = {
  id: 'post-id',
  author_id: 'author-id',
  author: { id: 'author-id', username: 'author' },
  content: 'A learning update',
  visibility: 'PUBLIC' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function renderCard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false }, mutations: { retry: false } },
  })
  queryClient.setQueryData(['engagement', post.id], {
    likeCount: 2,
    commentCount: 4,
    likedByUserIds: new Set<string>(),
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><PostCard post={post} onDeleted={vi.fn()} /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PostCard optimistic likes', () => {
  beforeEach(() => {
    vi.mocked(getPostEngagement).mockResolvedValue({ likeCount: 2, commentCount: 4, likedByUserIds: new Set() })
  })

  it('rolls the optimistic like count back when the request fails', async () => {
    let rejectRequest: ((error: Error) => void) | undefined
    vi.mocked(setPostLike).mockImplementation(() => new Promise((_resolve, reject) => {
      rejectRequest = reject
    }))
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Like post, 2 likes' }))
    expect(await screen.findByRole('button', { name: 'Unlike post, 3 likes' })).toBeInTheDocument()
    await act(async () => rejectRequest?.(new Error('Network unavailable')))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Like post, 2 likes' })).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent('Network unavailable')
  })
})