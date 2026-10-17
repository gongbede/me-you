import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest } from '../api/client'
import { MyVideosPanel } from './MediaLibraryPage'
import { VideoWatchPage } from './VideoWatchPage'

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>()
  return { ...original, apiRequest: vi.fn() }
})
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner-1', username: 'owner' } }),
}))

const request = vi.mocked(apiRequest)
const video = {
  id: 'video-1',
  owner_id: 'owner-1',
  media_asset_id: 'asset-1',
  title: 'My video',
  description: 'Video details',
  category: 'Education',
  visibility: 'PRIVATE' as const,
  view_count: 5,
  like_count: 2,
  liked_by_me: false,
}

function renderWatch(initialEntry = '/videos/video-1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[initialEntry]}><Routes><Route path="/videos/:videoId" element={<VideoWatchPage />} /></Routes></MemoryRouter></QueryClientProvider>)
}

function renderMine() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter><MyVideosPanel onChanged={() => undefined} /></MemoryRouter></QueryClientProvider>)
}

describe('Video library management and watch page', () => {
  beforeEach(() => request.mockReset())
  afterEach(() => cleanup())

  it('lists owned videos, edits visibility and saves changes', async () => {
    request.mockImplementation(async (path) => {
      if (path === '/api/v1/videos?mine=true&limit=50') return [video] as never
      if (path === '/api/v1/videos/video-1') return video as never
      return undefined as never
    })
    renderMine()
    expect(await screen.findByText('My video')).toBeInTheDocument()
    expect(screen.getByText('PRIVATE')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Updated video' } })
    fireEvent.change(screen.getByLabelText('Visibility'), { target: { value: 'PUBLIC' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/v1/videos/video-1', expect.objectContaining({
      method: 'PUT',
      body: expect.objectContaining({ title: 'Updated video', visibility: 'PUBLIC' }),
    })))
  })

  it('requires confirmation before deleting an owned video', async () => {
    request.mockImplementation(async (path, options) => {
      if (path === '/api/v1/videos?mine=true&limit=50') return [video] as never
      if (options?.method === 'DELETE') return undefined as never
      return undefined as never
    })
    renderMine()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Delete video?' })
    expect(dialog).toBeInTheDocument()
    expect(request).not.toHaveBeenCalledWith('/api/v1/videos/video-1', expect.objectContaining({ method: 'DELETE' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    const confirmation = await screen.findByRole('alertdialog')
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/v1/videos/video-1', expect.objectContaining({ method: 'DELETE' })))
  })

  it('shows loading, error and not-found watch states', async () => {
    let resolveVideo: ((value: unknown) => void) | undefined
    request.mockImplementation((path) => {
      if (path === '/api/v1/videos/video-1') return new Promise((resolve) => { resolveVideo = resolve }) as never
      return Promise.resolve(undefined) as never
    })
    const view = renderWatch()
    expect(screen.getByRole('status')).toHaveTextContent('Loading video')
    resolveVideo?.(video)
    view.unmount()

    request.mockRejectedValueOnce(new Error('Service offline'))
    renderWatch()
    expect(await screen.findByRole('heading', { name: 'Video unavailable' })).toBeInTheDocument()

    request.mockRejectedValueOnce(new ApiError('Video not found', 404))
    renderWatch()
    expect(await screen.findByRole('heading', { name: 'Video not found' })).toBeInTheDocument()
  })

  it('opens the video report dialog from the watch page', async () => {
    request.mockImplementation(async (path) => {
      if (path === '/api/v1/videos/video-1') return { ...video, owner_id: 'someone-else' } as never
      if (typeof path === 'string' && path.endsWith('/download')) return { download_url: 'https://media.example.test/video' } as never
      if (typeof path === 'string' && path.includes('/comments')) return [] as never
      return undefined as never
    })
    renderWatch()
    fireEvent.click(await screen.findByRole('button', { name: 'Report' }))
    expect(await screen.findByRole('dialog', { name: 'Report video' })).toBeInTheDocument()
  })
})
