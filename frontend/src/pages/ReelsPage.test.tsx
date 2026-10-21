import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getReelsPage, type Reel } from '../api/reels'
import { setPostLike } from '../api/social'
import { ReelsViewer } from './ReelsPage'

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'viewer-id', username: 'viewer' } }),
}))

vi.mock('../api/reels', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/reels')>(),
  getReelLimits: vi.fn(),
  getReelsPage: vi.fn(),
  deleteReel: vi.fn(),
}))

vi.mock('../api/social', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/social')>(),
  setPostLike: vi.fn(),
}))

vi.mock('../components/CommentsSection', () => ({ CommentsSection: () => <div>Comments panel</div> }))
vi.mock('../components/UserIdentity', () => ({ UserIdentity: ({ username }: { username: string }) => <span>{username}</span> }))

const reel: Reel = {
  id: 'reel-id',
  author_id: 'author-id',
  author: { id: 'author-id', username: 'author', display_name: 'Author', avatar_url: null },
  content: 'A short video',
  visibility: 'PUBLIC',
  post_type: 'REEL',
  media_asset_id: 'asset-id',
  video_url: '/video.mp4',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  edited: false,
  attachments: [],
  like_count: 2,
  comment_count: 1,
  liked_by_me: false,
}

function renderViewer() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><ReelsViewer /></MemoryRouter></QueryClientProvider>)
}

describe('ReelsViewer', () => {
  beforeEach(() => {
    vi.mocked(getReelsPage).mockResolvedValue({ items: [], offset: 0, limit: 10, has_more: false, next_cursor: null })
    vi.mocked(setPostLike).mockResolvedValue(undefined)
  })

  it('renders a helpful empty state', async () => {
    renderViewer()
    expect(await screen.findByRole('heading', { name: 'No Reels yet' })).toBeInTheDocument()
  })

  it('rolls an optimistic like back when the request fails', async () => {
    vi.mocked(getReelsPage).mockResolvedValue({ items: [reel], offset: 0, limit: 10, has_more: false, next_cursor: null })
    let rejectRequest: ((error: Error) => void) | undefined
    vi.mocked(setPostLike).mockImplementation(() => new Promise((_resolve, reject) => {
      rejectRequest = reject
    }))
    renderViewer()

    fireEvent.click(await screen.findByRole('button', { name: 'Like Reel, 2 likes' }))
    expect(await screen.findByRole('button', { name: 'Unlike Reel, 3 likes' })).toBeInTheDocument()
    await act(async () => rejectRequest?.(new Error('Network unavailable')))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Like Reel, 2 likes' })).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent('Network unavailable')
  })
})