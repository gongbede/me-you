import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { apiRequest } from '../api/client'
import { VideosPage } from './MediaLibraryPage'

vi.mock('../api/client', () => ({
  apiRequest: vi.fn(),
  getFriendlyErrorMessage: (error: unknown) => error instanceof Error ? error.message : 'Request failed',
}))

vi.mock('../hooks/useMusicPlayer', () => ({
  useMusicPlayer: () => ({ playQueue: vi.fn() }),
}))

describe('MediaLibraryPage', () => {
  afterEach(cleanup)

  it('opens and closes the video upload form on request', async () => {
    vi.mocked(apiRequest).mockResolvedValue([] as never)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><VideosPage /></MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.queryByRole('heading', { name: 'Upload a video' })).not.toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: 'Upload video' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(await screen.findByRole('heading', { name: 'Upload a video' })).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Close upload form' }))
    expect(screen.queryByRole('heading', { name: 'Upload a video' })).not.toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })
})