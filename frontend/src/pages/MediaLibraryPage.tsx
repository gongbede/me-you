import { useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Music2, Video } from 'lucide-react'
import { apiRequest, getFriendlyErrorMessage } from '../api/client'
import { avatarUploadTransport } from '../api/avatar'
import { useMusicPlayer } from '../hooks/useMusicPlayer'

type MediaItem = {
  id: string
  media_asset_id: string
  title: string
  category: string
  description?: string
  artist_name?: string
  play_count?: number
  view_count?: number
}

const videoCategories = ['Education', 'Programming', 'Technology', 'Music', 'Entertainment', 'Sports', 'Lifestyle', 'Faith', 'Other']
const musicCategories = ['Afrobeats', 'R&B', 'Hip-hop', 'Gospel', 'Highlife', 'Amapiano', 'Pop', 'Reggae and Dancehall', 'Jazz', 'Rock', 'Classical', 'Instrumental', 'Other']

function MediaUpload({ kind, onUploaded }: { kind: 'video' | 'music'; onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [artist, setArtist] = useState('')
  const [category, setCategory] = useState((kind === 'video' ? videoCategories : musicCategories)[0])
  const [rights, setRights] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const maxBytes = kind === 'video' ? 200_000_000 : 30_000_000
      const accepted = kind === 'video'
        ? ['video/mp4', 'video/webm']
        : ['audio/mpeg', 'audio/mp4', 'audio/aac', 'audio/ogg', 'audio/wav', 'audio/x-wav']
      if (!accepted.includes(file.type) || file.size > maxBytes || file.size < 1) {
        throw new Error(`Choose a supported ${kind} file within the ${kind === 'video' ? '200 MB' : '30 MB'} limit.`)
      }
      if (kind === 'music' && !rights) throw new Error('Confirm your rights to share this audio.')
      setStatus('Uploading…')
      const intent = await avatarUploadTransport.createIntent({
        purpose: kind === 'video' ? 'VIDEO' : 'AUDIO',
        content_type: file.type,
        byte_size: file.size,
        original_filename: file.name,
      })
      await avatarUploadTransport.upload(intent.upload_url, intent.required_headers, file, () => undefined)
      const asset = await avatarUploadTransport.complete(intent.asset.id)
      if (asset.status !== 'READY') throw new Error('The media upload could not be verified.')
      setStatus('Publishing…')
      if (kind === 'video') {
        await apiRequest('/api/v1/videos', { method: 'POST', body: { media_asset_id: asset.id, title, category, description: '', visibility: 'PUBLIC' } })
      } else {
        await apiRequest('/api/v1/tracks', { method: 'POST', body: { media_asset_id: asset.id, title, artist_name: artist, category, visibility: 'PUBLIC', rights_confirmed: rights } })
      }
      setFile(null)
      setTitle('')
      setArtist('')
      setRights(false)
      setStatus('Published')
      onUploaded()
    } catch (caught) {
      setError(getFriendlyErrorMessage(caught))
      setStatus('')
    } finally {
      setBusy(false)
    }
  }

  return <form className="learning-section" onSubmit={(event) => void submit(event)}>
    <h2>Upload {kind === 'video' ? 'a video' : 'a track'}</h2>
    <label className="field"><span>Title</span><input required maxLength={120} value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
    {kind === 'music' && <label className="field"><span>Artist name</span><input required maxLength={120} value={artist} onChange={(event) => setArtist(event.currentTarget.value)} /></label>}
    <label className="field"><span>Category</span><select value={category} onChange={(event) => setCategory(event.currentTarget.value)}>{(kind === 'video' ? videoCategories : musicCategories).map((value) => <option key={value}>{value}</option>)}</select></label>
    <label className="field"><span>Media file · {kind === 'video' ? 'MP4/WebM, up to 200 MB' : 'MP3, M4A/AAC, OGG or WAV, up to 30 MB'}</span><input required type="file" accept={kind === 'video' ? 'video/mp4,video/webm' : 'audio/mpeg,audio/mp4,audio/aac,audio/ogg,audio/wav'} onChange={(event) => setFile(event.currentTarget.files?.[0] ?? null)} /></label>
    {kind === 'music' && <label><input type="checkbox" checked={rights} onChange={(event) => setRights(event.currentTarget.checked)} /> I own this audio or have permission to share it</label>}
    {error && <p className="form-alert" role="alert">{error}</p>}
    {status && <p role="status">{status}</p>}
    <button className="button button--primary" disabled={busy || !file}>{busy ? 'Please wait…' : 'Publish'}</button>
  </form>
}

function LibraryPage({ kind }: { kind: 'video' | 'music' }) {
  const queryClient = useQueryClient()
  const [category, setCategory] = useState('')
  const [search, setSearch] = useState('')
  const key = [kind, 'library', category, search]
  const itemsQuery = useQuery({
    queryKey: key,
    queryFn: () => {
      const params = new URLSearchParams({ limit: '50' })
      if (category) params.set('category', category)
      if (search.trim()) params.set('q', search.trim())
      return apiRequest<MediaItem[]>(`/api/v1/${kind === 'video' ? 'videos' : 'tracks'}?${params}`)
    },
  })
  const title = kind === 'video' ? 'Videos' : 'Music'
  const categories = kind === 'video' ? videoCategories : musicCategories
  const refresh = () => void queryClient.invalidateQueries({ queryKey: [kind, 'library'] })
  return <div className="page-stack" data-section={kind === 'video' ? 'videos' : 'music'}>
    <header className="page-heading-row learning-heading"><div><span className="eyebrow">DISCOVER</span><h1>{title}</h1><p>{kind === 'video' ? 'Browse and share videos from the community.' : 'Community-uploaded music only; no commercial catalogue.'}</p></div>{kind === 'video' ? <Video aria-hidden="true" /> : <Music2 aria-hidden="true" />}</header>
    <MediaUpload kind={kind} onUploaded={refresh} />
    <section className="learning-section" aria-label={`${title} library`}>
      <label className="field"><span>Search {title.toLowerCase()}</span><input value={search} maxLength={100} onChange={(event) => setSearch(event.currentTarget.value)} /></label>
      <div className="chip-row" role="group" aria-label={`${title} categories`}>
        <button className={`chip${!category ? ' is-active' : ''}`} type="button" onClick={() => setCategory('')}>All</button>
        {categories.map((value) => <button className={`chip${category === value ? ' is-active' : ''}`} key={value} type="button" onClick={() => setCategory(category === value ? '' : value)}>{value}</button>)}
      </div>
      {kind === 'music' && category && <button className="button button--outline" type="button" onClick={() => void apiRequest(`/api/v1/music/categories/${encodeURIComponent(category)}/follow`, { method: 'PUT' })}>Follow this category</button>}
      {itemsQuery.isPending ? <p role="status">Loading {title.toLowerCase()}…</p> : itemsQuery.isError ? <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(itemsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void itemsQuery.refetch()}>Retry</button></div> : itemsQuery.data.length === 0 ? <p>No {title.toLowerCase()} found. Try another category or share the first one.</p> : <div className="learning-grid">      {itemsQuery.data.map((item, index) => <MediaCard key={item.id} item={item} kind={kind} queue={itemsQuery.data} index={index} />)}</div>}
    </section>
  </div>
}

function MediaCard({ item, kind, queue, index }: { item: MediaItem; kind: 'video' | 'music'; queue: MediaItem[]; index: number }) {
  const player = useMusicPlayer()
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  async function loadMedia() {
    try {
      const result = await apiRequest<{ download_url: string }>(`/api/v1/media/${item.media_asset_id}/download`)
      setUrl(result.download_url)
      await apiRequest(`/api/v1/videos/${item.id}/view`, { method: 'POST' })
    } catch (caught) {
      setError(getFriendlyErrorMessage(caught))
    }
  }
  return <article className="learning-card"><h2>{item.title}</h2><p>{kind === 'music' ? `${item.artist_name} · ` : ''}{item.category}</p>{url && kind === 'video' && <video src={url} controls playsInline aria-label={item.title} />}{error && <p className="form-alert" role="alert">{error}</p>}{kind === 'video' ? <button className="button button--outline" type="button" onClick={() => void loadMedia()}>Watch</button> : <button className="button button--outline" type="button" onClick={() => void player.playQueue(queue, index)}>Play</button>}</article>
}

export function VideosPage() { return <LibraryPage kind="video" /> }
export function MusicPage() { return <LibraryPage kind="music" /> }
