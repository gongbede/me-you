import { useRef, useState, type ReactNode } from 'react'
import { Music2, SkipBack, SkipForward } from 'lucide-react'
import { apiRequest, getFriendlyErrorMessage } from '../api/client'
import { MusicPlayerContext } from '../hooks/useMusicPlayer'

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

  const current = queue[index]
  return <MusicPlayerContext.Provider value={contextValue}>
    {children}
    {current && <aside className="music-mini-player" aria-label="Music player">
      <div className="music-mini-player__title"><Music2 size={18} aria-hidden="true" /><span>{current.title}<small>{current.artist_name}</small></span></div>
      <button className="icon-button" type="button" aria-label="Previous track" onClick={() => void selectTrack(Math.max(0, index - 1))}><SkipBack size={18} aria-hidden="true" /></button>
      <audio ref={audioRef} src={url} controls onEnded={() => void selectTrack((index + 1) % queue.length)} aria-label={`Now playing ${current.title}`} />
      <button className="icon-button" type="button" aria-label="Next track" onClick={() => void selectTrack((index + 1) % queue.length)}><SkipForward size={18} aria-hidden="true" /></button>
      {error && <span className="form-alert" role="alert">{error}</span>}
    </aside>}
  </MusicPlayerContext.Provider>
}
