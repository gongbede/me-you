import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from '../api/client'
import { MusicPlayerProvider } from '../components/MusicPlayer'
import { isMusicSpaceShortcutAllowed } from '../components/musicPlayerKeyboard'
import { MusicPage } from './MediaLibraryPage'
import { MyTracksPanel, PlaylistDetailPage, PlaylistLibraryPanel, TrackDetailPage } from './MusicManagement'

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>()
  return { ...original, apiRequest: vi.fn() }
})
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'viewer-1', username: 'viewer' } }),
}))

const request = vi.mocked(apiRequest)
const firstTrack = { id: 'track-1', owner_id: 'owner-1', media_asset_id: 'asset-1', title: 'First', artist_name: 'Artist', category: 'Jazz', visibility: 'PUBLIC' as const, play_count: 2 }
const secondTrack = { ...firstTrack, id: 'track-2', title: 'Second' }
const playlist = { id: 'playlist-1', title: 'Road songs', visibility: 'PUBLIC' as const }

function renderWithProviders(children: React.ReactNode, initialEntry = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MusicPlayerProvider><MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter></MusicPlayerProvider></QueryClientProvider>)
}

beforeEach(() => request.mockReset())
afterEach(() => cleanup())

describe('music management', () => {
  it('creates a playlist', async () => {
    request.mockImplementation(async (path, options) => {
      if (path === '/api/v1/playlists' && options?.method === 'POST') return playlist as never
      if (path === '/api/v1/playlists') return [playlist] as never
      return undefined as never
    })
    renderWithProviders(<PlaylistLibraryPanel />)
    fireEvent.change(await screen.findByLabelText('New playlist title'), { target: { value: 'Road songs' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create playlist' }))
    await screen.findByRole('link', { name: 'Road songs' })
    expect(request).toHaveBeenCalledWith('/api/v1/playlists', expect.objectContaining({
      method: 'POST',
      body: { title: 'Road songs', visibility: 'PUBLIC' },
    }))
  })

  it('reorders tracks and removes one from a playlist', async () => {
    request.mockImplementation(async (path) => {
      if (path === '/api/v1/playlists/playlist-1') return { ...playlist, owner_id: 'viewer-1', tracks: [firstTrack, secondTrack] } as never
      return undefined as never
    })
    renderWithProviders(<Routes><Route path="/music/playlists/:playlistId" element={<PlaylistDetailPage />} /></Routes>, '/music/playlists/playlist-1')
    expect(await screen.findByRole('heading', { name: 'Road songs' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Move First down' }))
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/v1/playlists/playlist-1/order', expect.objectContaining({
      method: 'PUT',
      body: { track_ids: ['track-2', 'track-1'] },
    })))
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0])
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/v1/playlists/playlist-1/tracks/track-1', expect.objectContaining({ method: 'DELETE' })))
  })

  it('toggles and displays category follow state', async () => {
    let following = false
    request.mockImplementation(async (path, options) => {
      if (path === '/api/v1/music/categories/follows') return (following ? ['Afrobeats'] : []) as never
      if (path === '/api/v1/tracks?limit=50') return [] as never
      if (typeof path === 'string' && path.includes('/music/categories/Afrobeats/follow')) {
        following = options?.method !== 'DELETE'
      }
      return undefined as never
    })
    renderWithProviders(<MusicPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Afrobeats' }))
    const follow = await screen.findByRole('button', { name: 'Follow this category' })
    fireEvent.click(follow)
    expect(await screen.findByRole('button', { name: 'Following' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Following' }))
    expect(await screen.findByRole('button', { name: 'Follow this category' })).toBeInTheDocument()
  })

  it('loads the track detail, shows the rights notice and offers reporting', async () => {
    request.mockImplementation(async (path) => {
      if (path === '/api/v1/tracks/track-1') return firstTrack as never
      if (path === '/api/v1/media/asset-1/download') return { download_url: 'https://media.example.test/audio' } as never
      return undefined as never
    })
    renderWithProviders(<Routes><Route path="/music/tracks/:trackId" element={<TrackDetailPage />} /></Routes>, '/music/tracks/track-1')
    expect(await screen.findByRole('heading', { name: 'First' })).toBeInTheDocument()
    expect(screen.getByText(/uploader confirms they own this audio/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Report' }))
    expect(await screen.findByRole('dialog', { name: 'Report track' })).toBeInTheDocument()
  })

  it('edits and deletes owned tracks with rights confirmation and a delete dialog', async () => {
    const ownedTrack = { ...firstTrack, owner_id: 'viewer-1' }
    request.mockImplementation(async (path, options) => {
      if (path === '/api/v1/tracks?mine=true&limit=50') return [ownedTrack] as never
      if (path === '/api/v1/tracks/track-1' && options?.method === 'PUT') return ownedTrack as never
      return undefined as never
    })
    renderWithProviders(<MyTracksPanel />)
    expect(await screen.findByRole('heading', { name: 'First' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Updated title' } })
    const rightsCheckbox = screen.getByLabelText('I own this audio or have permission to share it')
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    fireEvent.click(rightsCheckbox)
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/v1/tracks/track-1', expect.objectContaining({
      method: 'PUT',
      body: expect.objectContaining({ title: 'Updated title', rights_confirmed: true }),
    })))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(await screen.findByRole('alertdialog', { name: 'Delete track?' })).toBeInTheDocument()
  })
})

describe('music player keyboard shortcut', () => {
  it('does not toggle Space when an input, button, or select is targeted', () => {
    const input = document.createElement('input')
    const button = document.createElement('button')
    const select = document.createElement('select')
    const main = document.createElement('main')
    expect(isMusicSpaceShortcutAllowed(input)).toBe(false)
    expect(isMusicSpaceShortcutAllowed(button)).toBe(false)
    expect(isMusicSpaceShortcutAllowed(select)).toBe(false)
    expect(isMusicSpaceShortcutAllowed(main)).toBe(true)
  })
})
