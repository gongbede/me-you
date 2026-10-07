import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getFeed } from '../api/social'
import { HomePage } from './HomePage'

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'viewer-id', username: 'viewer', email: 'viewer@example.test' } }),
}))

vi.mock('../api/social', () => ({
  createPost: vi.fn(),
  getFeed: vi.fn(),
}))

vi.mock('../components/PostCard', () => ({
  PostCard: ({ post }: { post: { content: string } }) => <article>{post.content}</article>,
}))

const makePost = (id: string, content: string) => ({
  id,
  author_id: 'author-id',
  author: { id: 'author-id', username: 'author', display_name: 'Author', avatar_url: null },
  content,
  visibility: 'PUBLIC' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  like_count: 0,
  comment_count: 0,
  liked_by_me: false,
})

describe('HomePage feed pagination', () => {
  beforeEach(() => {
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
    expect(getFeed).toHaveBeenNthCalledWith(2, 'cursor-next')
  })
})