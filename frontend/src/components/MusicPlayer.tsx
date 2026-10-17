import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Music2, SkipBack, SkipForward } from 'lucide-react'
import { apiRequest, getFriendlyErrorMessage } from '../api/client'
import { MusicPlayerContext } from '../hooks/useMusicPlayer'
import { isMusicSpaceShortcutAllowed } from './musicPlayerKeyboard'

export type PlayableTrack = {
  id: string
  media_asset_id: string
  title: string
  artist_name?: string
}

export function MusicPlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const queueRef = useRef<PlayableTrack[]>([])
  const [queue, setQueue] = useState<PlayableTrack[]>([])
  const [index, setIndex] = useState(-1)
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const current = queue[index]
  const [playlistId, setPlaylistId] = useState('')
  const queryClient = useQueryClient()
  const playlistsQuery = useQuery({
    queryKey: ['music', 'playlists'],
    queryFn: () => apiRequest<Array<{ id: string; title: string }>>('/api/v1/playlists'),
    enabled: Boolean(current),
  })
  const addToPlaylist = useMutation({
    mutationFn: () => {
      if (!current || !playlistId) throw new Error('Choose a playlist first.')
      return apiRequest(`/api/v1/playlists/${playlistId}/tracks/${current.id}`, { method: 'POST' })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['music', 'playlist', playlistId] }),
  })

  async function selectTrack(nextIndex: number, nextQueue = queueRef.current) {
    const track = nextQueue[nextIndex]
    if (!track) return
    try {
      setError('')
      const media = await apiRequest<{ download_url: string }>(`/api/v1/media/${track.media_asset_id}/download`)
      await apiRequest(`/api/v1/tracks/${track.id}/play`, { method: 'POST' })
      queueRef.current = nextQueue
      setQueue(nextQueue)
      setIndex(nextIndex)
      setUrl(media.download_url)
      if (window.navigator.mediaSession && typeof MediaMetadata !== 'undefined') {
        window.navigator.mediaSession.metadata = new MediaMetadata({
          title: track.title,
          artist: track.artist_name ?? 'Me&You',
          album: 'Me&You Music',
        })
      }
      window.navigator.mediaSession?.setActionHandler?.('previoustrack', () => void selectTrack(Math.max(0, nextIndex - 1)))
      window.navigator.mediaSession?.setActionHandler?.('nexttrack', () => void selectTrack((nextIndex + 1) % nextQueue.length))
      window.setTimeout(() => void audioRef.current?.play().catch(() => undefined), 0)
    } catch (caught) {
      setError(getFriendlyErrorMessage(caught))
    }
  }

  const contextValue = {
    playQueue: (tracks: PlayableTrack[], selected: number) => selectTrack(selected, tracks),
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.code !== 'Space' || event.repeat) return
      if (!isMusicSpaceShortcutAllowed(event.target)) return
      if (!audioRef.current) return
      event.preventDefault()
      if (audioRef.current.paused) void audioRef.current.play().catch((caught: unknown) => setError(getFriendlyErrorMessage(caught)))
      else audioRef.current.pause()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return <MusicPlayerContext.Provider value={contextValue}>
    {children}
    {current && <aside className="music-mini-player" aria-label="Music player">
      <div className="music-mini-player__title"><Music2 size={18} aria-hidden="true" /><span><Link to={`/music/tracks/${current.id}`}>{current.title}</Link><small>{current.artist_name}</small></span></div>
      <button className="icon-button" type="button" aria-label="Previous track" onClick={() => void selectTrack(Math.max(0, index - 1))}><SkipBack size={18} aria-hidden="true" /></button>
      <audio ref={audioRef} src={url} controls onEnded={() => void selectTrack((index + 1) % queue.length)} aria-label={`Now playing ${current.title}`} />
      <button className="icon-button" type="button" aria-label="Next track" onClick={() => void selectTrack((index + 1) % queue.length)}><SkipForward size={18} aria-hidden="true" /></button>
      {playlistsQuery.isPending ? <span role="status">Loading playlists…</span> : playlistsQuery.isError ? <span role="alert">{getFriendlyErrorMessage(playlistsQuery.error)}</span> : playlistsQuery.data.length > 0 && <span className="music-mini-player__playlist">
        <label><span className="sr-only">Add current track to playlist</span><select aria-label="Add current track to playlist" value={playlistId} onChange={(event) => setPlaylistId(event.currentTarget.value)}><option value="">Add to playlist…</option>{playlistsQuery.data.map((playlist) => <option key={playlist.id} value={playlist.id}>{playlist.title}</option>)}</select></label>
        <button className="button button--outline" type="button" disabled={!playlistId || addToPlaylist.isPending} onClick={() => addToPlaylist.mutate()}>Add</button>
      </span>}
      {addToPlaylist.isError && <span role="alert">{getFriendlyErrorMessage(addToPlaylist.error)}</span>}
      {addToPlaylist.isSuccess && <span role="status">Added</span>}
      {error && <span className="form-alert" role="alert">{error}</span>}
    </aside>}
  </MusicPlayerContext.Provider>
}
