import { QueryClient, QueryClientProvider, useInfiniteQuery } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setPostLike } from '../api/social'
import { PostCard } from './PostCard'

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'viewer-id', username: 'viewer', email: 'viewer@example.test' } }),
}))

vi.mock('../api/social', () => ({
  deletePost: vi.fn(),
  setPostLike: vi.fn(),
  updatePost: vi.fn(),
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
  post_type: 'POST' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  edited: false,
  attachments: [],
  like_count: 2,
  comment_count: 4,
  liked_by_me: false,
}

const feedPage = { items: [post], offset: 0, limit: 20, has_more: false, next_cursor: null }

function renderCard(card = post) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false }, mutations: { retry: false } },
  })
  queryClient.setQueryData(['feed'], {
    pages: [{ ...feedPage, items: [card] }],
    pageParams: [undefined],
  })

  function FeedCard() {
    const feedQuery = useInfiniteQuery({
      queryKey: ['feed'],
      queryFn: async () => feedPage,
      initialPageParam: undefined as string | undefined,
      getNextPageParam: (page) => page.next_cursor ?? undefined,
      enabled: false,
    })
    const feedPost = feedQuery.data?.pages[0]?.items[0] ?? card
    return <PostCard post={feedPost} onDeleted={vi.fn()} />
  }

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><FeedCard /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PostCard optimistic likes', () => {
  afterEach(cleanup)
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

describe('PostCard owner tools and images', () => {
  afterEach(cleanup)
  it('edits a post inline and shows the edited marker', async () => {
    const { updatePost } = await import('../api/social')
    vi.mocked(updatePost).mockResolvedValue({ ...post, content: 'Updated post', edited: true })
    renderCard({ ...post, author_id: 'viewer-id' })

    fireEvent.click(screen.getByRole('button', { name: 'Edit post' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Edit post' }), { target: { value: 'Updated post' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(updatePost).toHaveBeenCalledWith('post-id', { content: 'Updated post' }))
    expect(await screen.findByText('Updated post')).toBeInTheDocument()
    expect(await screen.findByText('Edited')).toBeInTheDocument()
  })

  it('opens an image viewer that supports next, keyboard navigation, and Escape', async () => {
    const card = {
      ...post,
      attachments: [
        { id: 'image-1', media_asset_id: 'asset-1', image_url: '/one.png', alt_text: 'First', position: 0 },
        { id: 'image-2', media_asset_id: 'asset-2', image_url: '/two.png', alt_text: 'Second', position: 1 },
      ],
    }
    renderCard(card)

    fireEvent.click(screen.getByRole('button', { name: 'Open image 1 of 2' }))
    const dialog = screen.getByRole('dialog', { name: 'Post image viewer' })
    expect(dialog).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close image viewer' })).toHaveFocus()
    expect(within(dialog).getByRole('img', { name: 'First' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next image' }))
    expect(within(dialog).getByRole('img', { name: 'Second' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(within(dialog).getByRole('img', { name: 'First' })).toBeInTheDocument()
    fireEvent.keyDown(document.activeElement ?? window, { key: 'Tab', shiftKey: true })
    expect(screen.getByRole('button', { name: 'Next image' })).toHaveFocus()
    fireEvent.keyDown(document.activeElement ?? window, { key: 'Tab' })
    expect(screen.getByRole('button', { name: 'Close image viewer' })).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open image 1 of 2' })).toHaveFocus()
  })

  it('asks for confirmation before deleting and copies a post anchor URL', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderCard({ ...post, author_id: 'viewer-id' })

    fireEvent.click(screen.getByRole('button', { name: 'Copy post link' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Link copied')
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('#post-post-id'))
    fireEvent.click(screen.getByRole('button', { name: 'Delete post' }))
    expect(window.confirm).toHaveBeenCalledWith('Delete this post?')
  })
})