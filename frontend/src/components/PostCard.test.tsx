import { QueryClient, QueryClientProvider, useInfiniteQuery } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setPostLike } from '../api/social'
import { PostCard } from './PostCard'

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'viewer-id', username: 'viewer', email: 'viewer@example.test' } }),
}))

vi.mock('../api/social', () => ({
  deletePost: vi.fn(),
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
  author: { id: 'author-id', username: 'author', display_name: 'Author', avatar_url: null },
  content: 'A learning update',
  visibility: 'PUBLIC' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  like_count: 2,
  comment_count: 4,
  liked_by_me: false,
}

const feedPage = { items: [post], offset: 0, limit: 20, has_more: false, next_cursor: null }

function renderCard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false }, mutations: { retry: false } },
  })
  queryClient.setQueryData(['feed'], { pages: [feedPage], pageParams: [undefined] })

  function FeedCard() {
    const feedQuery = useInfiniteQuery({
      queryKey: ['feed'],
      queryFn: async () => feedPage,
      initialPageParam: undefined as string | undefined,
      getNextPageParam: (page) => page.next_cursor ?? undefined,
      enabled: false,
    })
    const feedPost = feedQuery.data?.pages[0]?.items[0] ?? post
    return <PostCard post={feedPost} onDeleted={vi.fn()} />
  }

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><FeedCard /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PostCard optimistic likes', () => {
  beforeEach(() => {
    vi.mocked(setPostLike).mockResolvedValue(undefined)
  })

  it('updates the feed post after a successful like', async () => {
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Like post, 2 likes' }))

    expect(await screen.findByRole('button', { name: 'Unlike post, 3 likes' })).toBeInTheDocument()
    expect(setPostLike).toHaveBeenCalledWith('post-id', true)
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