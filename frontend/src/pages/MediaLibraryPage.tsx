import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Music2, Plus, Video, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { apiRequest, getFriendlyErrorMessage } from '../api/client'
import { avatarUploadTransport } from '../api/avatar'
import { PageHeader } from '../components/PageHeader'
import { useMusicPlayer } from '../hooks/useMusicPlayer'
import { MyTracksPanel, PlaylistLibraryPanel } from './MusicManagement'

type MediaItem = {
  id: string
  media_asset_id: string
  title: string
  category: string
  description?: string
  artist_name?: string
  play_count?: number
  view_count?: number
  visibility: 'PUBLIC' | 'FOLLOWERS' | 'PRIVATE'
}

const videoCategories = ['Education', 'Programming', 'Technology', 'Music', 'Entertainment', 'Sports', 'Lifestyle', 'Faith', 'Other']
const musicCategories = ['Afrobeats', 'R&B', 'Hip-hop', 'Gospel', 'Highlife', 'Amapiano', 'Pop', 'Reggae and Dancehall', 'Jazz', 'Rock', 'Classical', 'Instrumental', 'Other']

function MediaUpload({ kind, onUploaded, onClose, id }: { kind: 'video' | 'music'; onUploaded: () => void; onClose: () => void; id: string }) {
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

  return <form id={id} className="learning-section media-upload-panel" onSubmit={(event) => void submit(event)}>
    <div className="media-upload-panel__heading"><h2>Upload {kind === 'video' ? 'a video' : 'a track'}</h2><button className="icon-button" type="button" aria-label="Close upload form" title="Close upload form" onClick={onClose}><X size={18} aria-hidden="true" /></button></div>
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
  const [tab, setTab] = useState<'discover' | 'mine' | 'playlists'>('discover')
  const [isUploadOpen, setIsUploadOpen] = useState(false)
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
  const followsQuery = useQuery({
    queryKey: ['music', 'category-follows'],
    queryFn: () => apiRequest<string[]>('/api/v1/music/categories/follows'),
    enabled: kind === 'music',
  })
  const followMutation = useMutation({
    mutationFn: (following: boolean) => {
      if (!category) throw new Error('Choose a category first.')
      const method = following ? 'DELETE' : 'PUT'
      return apiRequest(`/api/v1/music/categories/${encodeURIComponent(category)}/follow`, { method })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['music', 'category-follows'] }),
  })
  const title = kind === 'video' ? 'Videos' : 'Music'
  const categories = kind === 'video' ? videoCategories : musicCategories
  const refresh = () => void queryClient.invalidateQueries({ queryKey: [kind, 'library'] })
  return <div className="page-stack" data-section={kind === 'video' ? 'videos' : 'music'}>
    <PageHeader
      section="DISCOVER"
      title={title}
      description={kind === 'video' ? 'Browse and share videos from the community.' : 'Community-uploaded music only; no commercial catalogue.'}
      action={<button className="button button--primary" type="button" aria-expanded={isUploadOpen} aria-controls="media-upload-form" onClick={() => setIsUploadOpen((open) => !open)}><Plus size={16} aria-hidden="true" />{isUploadOpen ? 'Close upload' : kind === 'video' ? 'Upload video' : 'Upload track'}</button>}
    />
    {isUploadOpen && <MediaUpload id="media-upload-form" kind={kind} onClose={() => setIsUploadOpen(false)} onUploaded={() => { refresh(); setIsUploadOpen(false) }} />}
    {kind === 'video' && <div className="chip-row" role="tablist" aria-label="Video sections">
      <button className={`chip${tab === 'discover' ? ' is-active' : ''}`} role="tab" aria-selected={tab === 'discover'} type="button" onClick={() => setTab('discover')}>Discover</button>
      <button className={`chip${tab === 'mine' ? ' is-active' : ''}`} role="tab" aria-selected={tab === 'mine'} type="button" onClick={() => setTab('mine')}>My videos</button>
    </div>}
    {kind === 'music' && <div className="chip-row" role="tablist" aria-label="Music sections">
      <button className={`chip${tab === 'discover' ? ' is-active' : ''}`} role="tab" aria-selected={tab === 'discover'} type="button" onClick={() => setTab('discover')}>Tracks</button>
      <button className={`chip${tab === 'playlists' ? ' is-active' : ''}`} role="tab" aria-selected={tab === 'playlists'} type="button" onClick={() => setTab('playlists')}>Playlists</button>
      <button className={`chip${tab === 'mine' ? ' is-active' : ''}`} role="tab" aria-selected={tab === 'mine'} type="button" onClick={() => setTab('mine')}>My tracks</button>
    </div>}
    {tab === 'mine' && kind === 'video' ? <MyVideosPanel onChanged={refresh} /> : <>
    {kind === 'music' && tab === 'playlists' ? <PlaylistLibraryPanel /> : kind === 'music' && tab === 'mine' ? <MyTracksPanel /> : <>
    <section className="learning-section" aria-label={`${title} library`}>
      <label className="field"><span>Search {title.toLowerCase()}</span><input value={search} maxLength={100} onChange={(event) => setSearch(event.currentTarget.value)} /></label>
      <div className="chip-row" role="group" aria-label={`${title} categories`}>
        <button className={`chip${!category ? ' is-active' : ''}`} type="button" onClick={() => setCategory('')}>All</button>
        {categories.map((value) => <button className={`chip${category === value ? ' is-active' : ''}`} key={value} type="button" onClick={() => setCategory(category === value ? '' : value)}>{value}</button>)}
      </div>
      {kind === 'music' && category && <div>
        {followsQuery.isPending ? <p role="status">Loading follow status…</p> : followsQuery.isError ? <p role="alert" className="form-alert">{getFriendlyErrorMessage(followsQuery.error)}</p> : <button className="button button--outline" type="button" disabled={followMutation.isPending} onClick={() => followMutation.mutate(followsQuery.data.includes(category))}>{followsQuery.data.includes(category) ? 'Following' : 'Follow this category'}</button>}
        {followMutation.isError && <p role="alert" className="form-alert">{getFriendlyErrorMessage(followMutation.error)}</p>}
      </div>}
      {itemsQuery.isPending ? <p role="status">Loading {title.toLowerCase()}…</p> : itemsQuery.isError ? <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(itemsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void itemsQuery.refetch()}>Retry</button></div> : itemsQuery.data.length === 0 ? <p>No {title.toLowerCase()} found. Try another category or share the first one.</p> : <div className="learning-grid">      {itemsQuery.data.map((item, index) => <MediaCard key={item.id} item={item} kind={kind} queue={itemsQuery.data} index={index} />)}</div>}
    </section>
    </>}
    </>}
  </div>
}

export function MyVideosPanel({ onChanged }: { onChanged: () => void }) {
  const queryClient = useQueryClient()
  const videosQuery = useQuery({
    queryKey: ['videos', 'mine'],
    queryFn: () => apiRequest<MediaItem[]>('/api/v1/videos?mine=true&limit=50'),
  })
  const [editing, setEditing] = useState<MediaItem | null>(null)
  const [deleting, setDeleting] = useState<MediaItem | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState(videoCategories[0])
  const [visibility, setVisibility] = useState<MediaItem['visibility']>('PUBLIC')
  const [actionError, setActionError] = useState('')
  const saveMutation = useMutation({
    mutationFn: () => {
      if (!editing) throw new Error('Select a video to edit.')
      return apiRequest(`/api/v1/videos/${editing.id}`, { method: 'PUT', body: { title, description, category, visibility } })
    },
    onSuccess: async () => {
      setEditing(null)
      await queryClient.invalidateQueries({ queryKey: ['videos', 'mine'] })
      onChanged()
    },
    onError: (error) => setActionError(getFriendlyErrorMessage(error)),
  })
  const deleteMutation = useMutation({
    mutationFn: (video: MediaItem) => apiRequest(`/api/v1/videos/${video.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      setDeleting(null)
      await queryClient.invalidateQueries({ queryKey: ['videos', 'mine'] })
      onChanged()
    },
    onError: (error) => setActionError(getFriendlyErrorMessage(error)),
  })
  if (videosQuery.isPending) return <p role="status">Loading your videos…</p>
  if (videosQuery.isError) return <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(videosQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void videosQuery.refetch()}>Retry</button></div>
  return <section className="learning-section" aria-label="My videos">
    {videosQuery.data.length === 0 ? <p>You haven’t published any videos yet.</p> : <div className="learning-grid">{videosQuery.data.map((item) => <article className="learning-card" key={item.id}>
      <h2><Link to={`/videos/${item.id}`}>{item.title}</Link></h2>
      <p>{item.category} · <span className="chip">{item.visibility}</span></p>
      <button className="button button--outline" type="button" onClick={() => {
        setEditing(item)
        setTitle(item.title)
        setDescription(item.description ?? '')
        setCategory(item.category)
        setVisibility(item.visibility)
        setActionError('')
      }}>Edit</button>
      <button className="button button--quiet" type="button" onClick={() => { setDeleting(item); setActionError('') }}>Delete</button>
    </article>)}</div>}
    {actionError && <p className="form-alert" role="alert">{actionError}</p>}
    {editing && <div className="report-dialog-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="edit-video-title" className="report-dialog">
      <h2 id="edit-video-title">Edit video</h2>
      <form onSubmit={(event) => { event.preventDefault(); saveMutation.mutate() }}>
        <label className="field"><span>Title</span><input required maxLength={120} value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
        <label className="field"><span>Description</span><textarea maxLength={2000} value={description} onChange={(event) => setDescription(event.currentTarget.value)} /></label>
        <label className="field"><span>Category</span><select value={category} onChange={(event) => setCategory(event.currentTarget.value)}>{videoCategories.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="field"><span>Visibility</span><select value={visibility} onChange={(event) => setVisibility(event.currentTarget.value as MediaItem['visibility'])}><option>PUBLIC</option><option>FOLLOWERS</option><option>PRIVATE</option></select></label>
        {actionError && <p className="form-alert" role="alert">{actionError}</p>}
        <button className="button button--primary" type="submit" disabled={saveMutation.isPending}>Save</button>
        <button className="button button--outline" type="button" onClick={() => setEditing(null)}>Cancel</button>
      </form>
    </section></div>}
    {deleting && <div className="report-dialog-backdrop"><section role="alertdialog" aria-modal="true" aria-labelledby="delete-video-title" className="report-dialog">
      <h2 id="delete-video-title">Delete video?</h2><p>This will permanently delete “{deleting.title}”.</p>
      {actionError && <p className="form-alert" role="alert">{actionError}</p>}
      <button className="button button--quiet" type="button" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(deleting)}>Delete</button>
      <button className="button button--outline" type="button" onClick={() => setDeleting(null)}>Cancel</button>
    </section></div>}
  </section>
}

function MediaCard({ item, kind, queue, index }: { item: MediaItem; kind: 'video' | 'music'; queue: MediaItem[]; index: number }) {
  const player = useMusicPlayer()
  const PlaceholderIcon = kind === 'video' ? Video : Music2
  return <article className="learning-card media-card">
    <div className={`media-card__thumbnail media-card__thumbnail--${kind}`} aria-hidden="true"><PlaceholderIcon size={30} /></div>
    <div className="media-card__content">
      <div className="media-card__meta"><span className="chip">{item.category}</span><span>{kind === 'music' ? item.artist_name : 'Community video'}</span></div>
      <h2>{kind === 'video' ? <Link to={`/videos/${item.id}`}>{item.title}</Link> : <Link to={`/music/tracks/${item.id}`}>{item.title}</Link>}</h2>
      {kind === 'video' ? <Link className="button button--outline" to={`/videos/${item.id}`}>Watch</Link> : <><button className="button button--outline" type="button" onClick={() => void player.playQueue(queue, index)}>Play</button><AddToPlaylistButton trackId={item.id} /></>}
    </div>
  </article>
}

function AddToPlaylistButton({ trackId }: { trackId: string }) {
  const queryClient = useQueryClient()
  const playlists = useQuery({ queryKey: ['music', 'playlists'], queryFn: () => apiRequest<Array<{ id: string; title: string }>>('/api/v1/playlists') })
  const [playlistId, setPlaylistId] = useState('')
  const mutation = useMutation({
    mutationFn: () => apiRequest(`/api/v1/playlists/${playlistId}/tracks/${trackId}`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['music', 'playlist', playlistId] }),
  })
  if (playlists.isPending) return <span role="status">Loading playlists…</span>
  if (playlists.isError) return <span role="alert">{getFriendlyErrorMessage(playlists.error)}</span>
  if (playlists.data.length === 0) return <Link className="button button--outline" to="/music">Create a playlist</Link>
  return <span>
    <label className="field"><span>Add to playlist</span><select aria-label="Add to playlist" value={playlistId} onChange={(event) => setPlaylistId(event.currentTarget.value)}><option value="">Choose playlist</option>{playlists.data.map((playlist) => <option key={playlist.id} value={playlist.id}>{playlist.title}</option>)}</select></label>
    <button className="button button--outline" type="button" disabled={!playlistId || mutation.isPending} onClick={() => mutation.mutate()}>Add to playlist</button>
    {mutation.isError && <p role="alert" className="form-alert">{getFriendlyErrorMessage(mutation.error)}</p>}
    {mutation.isSuccess && <p role="status">Added to playlist.</p>}
  </span>
}

export function VideosPage() { return <LibraryPage kind="video" /> }
export function MusicPage() { return <LibraryPage kind="music" /> }
