import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getFeed } from '../api/social'
import { HomePage } from './HomePage'

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'viewer-id', username: 'viewer', email: 'viewer@example.test' } }),
}))

vi.mock('../api/social', () => ({
  createPost: vi.fn(),
  getFeed: vi.fn(),
}))

vi.mock('../api/media', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/media')>(),
  getPostImageLimits: vi.fn().mockResolvedValue({
    max_bytes: 10_000_000,
    content_types: ['image/jpeg', 'image/png', 'image/webp'],
  }),
}))

vi.mock('../components/PostCard', () => ({
  PostCard: ({ post }: { post: { content: string } }) => <article>{post.content}</article>,
}))

vi.mock('./ReelsPage', () => ({
  ReelsViewer: ({ embedded }: { embedded: boolean }) => <div data-testid="reels-viewer">{embedded ? 'Embedded Reels' : 'Reels'}</div>,
}))

const makePost = (id: string, content: string) => ({
  id,
  author_id: 'author-id',
  author: { id: 'author-id', username: 'author', display_name: 'Author', avatar_url: null },
  content,
  visibility: 'PUBLIC' as const,
  post_type: 'POST' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  edited: false,
  attachments: [],
  like_count: 0,
  comment_count: 0,
  liked_by_me: false,
})

describe('HomePage feed pagination', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })
  beforeEach(() => {
    sessionStorage.clear()
    vi.mocked(getFeed).mockReset()
    vi.mocked(getFeed)
      .mockResolvedValueOnce({ items: [makePost('one', 'First page')], offset: 0, limit: 20, has_more: true, next_cursor: 'cursor-next' })
      .mockResolvedValueOnce({ items: [makePost('two', 'Second page')], offset: 0, limit: 20, has_more: false, next_cursor: null })
  })

  it('requests the next cursor page when Load more is clicked', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    render(<QueryClientProvider client={queryClient}><MemoryRouter><HomePage /></MemoryRouter></QueryClientProvider>)

    expect(await screen.findByText('First page')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('Second page')).toBeInTheDocument()
    expect(getFeed).toHaveBeenNthCalledWith(2, 'cursor-next', 'FOLLOWING')
  })

  it('switches between Following and Latest feed modes', async () => {
    vi.mocked(getFeed).mockReset()
      .mockResolvedValueOnce({ items: [makePost('following', 'Following post')], offset: 0, limit: 20, has_more: false, next_cursor: null })
      .mockResolvedValueOnce({ items: [makePost('latest', 'Latest post')], offset: 0, limit: 20, has_more: false, next_cursor: null })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    render(<QueryClientProvider client={queryClient}><MemoryRouter><HomePage /></MemoryRouter></QueryClientProvider>)

    expect(await screen.findByText('Following post')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Latest' }))
    expect(await screen.findByText('Latest post')).toBeInTheDocument()
    expect(getFeed).toHaveBeenLastCalledWith(undefined, 'LATEST')
  })

  it('loads another page when the intersection sentinel becomes visible', async () => {
    class TestIntersectionObserver {
      private readonly callback: IntersectionObserverCallback
      constructor(callback: IntersectionObserverCallback) {
        this.callback = callback
      }
      observe(target: Element) {
        this.callback([{ isIntersecting: true, target } as IntersectionObserverEntry], this as unknown as IntersectionObserver)
      }
      disconnect() {}
      unobserve() {}
      takeRecords(): IntersectionObserverEntry[] { return [] }
    }
    vi.stubGlobal('IntersectionObserver', TestIntersectionObserver)
    vi.mocked(getFeed).mockReset()
      .mockResolvedValueOnce({ items: [makePost('one', 'First page')], offset: 0, limit: 20, has_more: true, next_cursor: 'cursor-next' })
      .mockResolvedValueOnce({ items: [makePost('two', 'Second page')], offset: 0, limit: 20, has_more: false, next_cursor: null })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    render(<QueryClientProvider client={queryClient}><MemoryRouter><HomePage /></MemoryRouter></QueryClientProvider>)

    expect(await screen.findByText('First page')).toBeInTheDocument()
    expect(await screen.findByText('Second page')).toBeInTheDocument()
    expect(getFeed).toHaveBeenNthCalledWith(2, 'cursor-next', 'FOLLOWING')
  })

  it('shows a jump button when a background refresh adds a newer post', async () => {
    vi.mocked(getFeed).mockReset().mockResolvedValue({
      items: [makePost('one', 'First page')], offset: 0, limit: 20, has_more: false, next_cursor: null,
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    render(<QueryClientProvider client={queryClient}><MemoryRouter><HomePage /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByText('First page')).toBeInTheDocument()
    queryClient.setQueryData(['feed', 'FOLLOWING'], {
      pages: [{ items: [makePost('new', 'New update'), makePost('one', 'First page')], offset: 0, limit: 20, has_more: false, next_cursor: null }],
      pageParams: [undefined],
    })

    const jumpButton = await screen.findByRole('button', { name: 'Jump to new posts' })
    fireEvent.click(jumpButton)
    expect(screen.queryByRole('button', { name: 'Jump to new posts' })).not.toBeInTheDocument()
  })

  it('remembers the last selected Home tab for the session', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    const view = render(<QueryClientProvider client={queryClient}><MemoryRouter><HomePage /></MemoryRouter></QueryClientProvider>)

    fireEvent.click(screen.getByRole('tab', { name: 'Reels' }))
    expect(await screen.findByTestId('reels-viewer')).toBeInTheDocument()
    expect(sessionStorage.getItem('home.activeTab')).toBe('reels')

    view.unmount()
    render(<QueryClientProvider client={queryClient}><MemoryRouter><HomePage /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByRole('tab', { name: 'Reels' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('reels-viewer')).toBeInTheDocument()
  })

  it('shows a useful empty state and focuses the composer action', async () => {
    vi.mocked(getFeed).mockReset().mockResolvedValue({
      items: [], offset: 0, limit: 20, has_more: false, next_cursor: null,
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
    render(<QueryClientProvider client={queryClient}><MemoryRouter><HomePage /></MemoryRouter></QueryClientProvider>)

    expect(await screen.findByText('No posts yet. Share the first update.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Write a post' }))
    expect(screen.getByLabelText('Share something with your community')).toHaveFocus()
  })
})