import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ApiError, apiRequest, getFriendlyErrorMessage } from '../api/client'
import { ReportDialog } from '../components/ReportDialog'
import { useMusicPlayer } from '../hooks/useMusicPlayer'
import { useAuth } from '../hooks/useAuth'

type Track = {
  id: string
  owner_id: string
  media_asset_id: string
  title: string
  artist_name: string
  category: string
  visibility: 'PUBLIC' | 'FOLLOWERS' | 'PRIVATE'
  play_count: number
}
type Playlist = { id: string; title: string; owner_id?: string; visibility: Track['visibility'] }
type PlaylistDetail = Playlist & { tracks: Track[] }
const categories = ['Afrobeats', 'R&B', 'Hip-hop', 'Gospel', 'Highlife', 'Amapiano', 'Pop', 'Reggae and Dancehall', 'Jazz', 'Rock', 'Classical', 'Instrumental', 'Other']

export function PlaylistLibraryPanel() {
  const queryClient = useQueryClient()
  const playlistsQuery = useQuery({
    queryKey: ['music', 'playlists'],
    queryFn: () => apiRequest<Playlist[]>('/api/v1/playlists'),
  })
  const [title, setTitle] = useState('')
  const [visibility, setVisibility] = useState<Track['visibility']>('PUBLIC')
  const createMutation = useMutation({
    mutationFn: () => apiRequest('/api/v1/playlists', { method: 'POST', body: { title, visibility } }),
    onSuccess: async () => {
      setTitle('')
      await queryClient.invalidateQueries({ queryKey: ['music', 'playlists'] })
    },
  })
  const [editing, setEditing] = useState<Playlist | null>(null)
  const [deleting, setDeleting] = useState<Playlist | null>(null)
  const editMutation = useMutation({
    mutationFn: () => {
      if (!editing) throw new Error('Select a playlist to edit.')
      return apiRequest(`/api/v1/playlists/${editing.id}`, { method: 'PUT', body: { title, visibility } })
    },
    onSuccess: async () => {
      setEditing(null)
      await queryClient.invalidateQueries({ queryKey: ['music', 'playlists'] })
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (playlist: Playlist) => apiRequest(`/api/v1/playlists/${playlist.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      setDeleting(null)
      await queryClient.invalidateQueries({ queryKey: ['music', 'playlists'] })
    },
  })
  if (playlistsQuery.isPending) return <p role="status">Loading playlists…</p>
  if (playlistsQuery.isError) return <div role="alert" className="inline-error"><p>{getFriendlyErrorMessage(playlistsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void playlistsQuery.refetch()}>Retry</button></div>
  return <section className="learning-section" aria-label="Playlists">
    <h2>Playlists</h2>
    <form onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); createMutation.mutate() }}>
      <label className="field"><span>New playlist title</span><input required maxLength={120} value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
      <label className="field"><span>Visibility</span><select value={visibility} onChange={(event) => setVisibility(event.currentTarget.value as Track['visibility'])}><option>PUBLIC</option><option>FOLLOWERS</option><option>PRIVATE</option></select></label>
      <button className="button button--primary" type="submit" disabled={!title.trim() || createMutation.isPending}>Create playlist</button>
    </form>
    {(createMutation.isError || editMutation.isError || deleteMutation.isError) && <p className="form-alert" role="alert">{getFriendlyErrorMessage(createMutation.error ?? editMutation.error ?? deleteMutation.error)}</p>}
    {playlistsQuery.data.length === 0 ? <p>No playlists yet. Create your first one above.</p> : <div className="learning-grid">{playlistsQuery.data.map((playlist) => <article className="learning-card" key={playlist.id}>
      <h3><Link to={`/music/playlists/${playlist.id}`}>{playlist.title}</Link></h3><p>{playlist.visibility}</p>
      <button className="button button--outline" type="button" onClick={() => { setEditing(playlist); setTitle(playlist.title); setVisibility(playlist.visibility) }}>Rename</button>
      <button className="button button--quiet" type="button" onClick={() => setDeleting(playlist)}>Delete</button>
    </article>)}</div>}
    {editing && <div className="report-dialog-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="edit-playlist-title" className="report-dialog">
      <h2 id="edit-playlist-title">Edit playlist</h2><form onSubmit={(event) => { event.preventDefault(); editMutation.mutate() }}>
        <label className="field"><span>Title</span><input required maxLength={120} value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
        <label className="field"><span>Visibility</span><select value={visibility} onChange={(event) => setVisibility(event.currentTarget.value as Track['visibility'])}><option>PUBLIC</option><option>FOLLOWERS</option><option>PRIVATE</option></select></label>
        <button className="button button--primary" type="submit" disabled={editMutation.isPending}>Save</button><button className="button button--outline" type="button" onClick={() => setEditing(null)}>Cancel</button>
      </form>
    </section></div>}
    {deleting && <div className="report-dialog-backdrop"><section role="alertdialog" aria-modal="true" aria-labelledby="delete-playlist-title" className="report-dialog">
      <h2 id="delete-playlist-title">Delete playlist?</h2><p>This will delete “{deleting.title}”.</p>
      <button className="button button--quiet" type="button" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(deleting)}>Delete</button><button className="button button--outline" type="button" onClick={() => setDeleting(null)}>Cancel</button>
    </section></div>}
  </section>
}

export function MyTracksPanel() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const tracksQuery = useQuery({
    queryKey: ['music', 'my-tracks'],
    queryFn: () => apiRequest<Track[]>('/api/v1/tracks?mine=true&limit=50'),
  })
  const [editing, setEditing] = useState<Track | null>(null)
  const [deleting, setDeleting] = useState<Track | null>(null)
  const [title, setTitle] = useState('')
  const [artist, setArtist] = useState('')
  const [category, setCategory] = useState(categories[0])
  const [visibility, setVisibility] = useState<Track['visibility']>('PUBLIC')
  const [rightsConfirmed, setRightsConfirmed] = useState(false)
  const editMutation = useMutation({
    mutationFn: () => {
      if (!editing) throw new Error('Select a track to edit.')
      return apiRequest(`/api/v1/tracks/${editing.id}`, { method: 'PUT', body: {
        media_asset_id: editing.media_asset_id, title, artist_name: artist, category, visibility, rights_confirmed: rightsConfirmed,
      } })
    },
    onSuccess: async () => {
      setEditing(null)
      await queryClient.invalidateQueries({ queryKey: ['music', 'my-tracks'] })
      await queryClient.invalidateQueries({ queryKey: ['music', 'library'] })
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (track: Track) => apiRequest(`/api/v1/tracks/${track.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      setDeleting(null)
      await queryClient.invalidateQueries({ queryKey: ['music', 'my-tracks'] })
      await queryClient.invalidateQueries({ queryKey: ['music', 'library'] })
    },
  })
  if (tracksQuery.isPending) return <p role="status">Loading your tracks…</p>
  if (tracksQuery.isError) return <div role="alert" className="inline-error"><p>{getFriendlyErrorMessage(tracksQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void tracksQuery.refetch()}>Retry</button></div>
  const tracks = tracksQuery.data.filter((track) => track.owner_id === user?.id)
  return <section className="learning-section" aria-label="My tracks">
    {tracks.length === 0 ? <p>You haven’t shared any tracks yet.</p> : <div className="learning-grid">{tracks.map((track) => <article className="learning-card" key={track.id}>
      <h2><Link to={`/music/tracks/${track.id}`}>{track.title}</Link></h2><p>{track.artist_name} · {track.category} · {track.visibility}</p>
      <button className="button button--outline" type="button" onClick={() => { setEditing(track); setTitle(track.title); setArtist(track.artist_name); setCategory(track.category); setVisibility(track.visibility); setRightsConfirmed(false) }}>Edit</button>
      <button className="button button--quiet" type="button" onClick={() => setDeleting(track)}>Delete</button>
    </article>)}</div>}
    {(editMutation.isError || deleteMutation.isError) && <p className="form-alert" role="alert">{getFriendlyErrorMessage(editMutation.error ?? deleteMutation.error)}</p>}
    {editing && <div className="report-dialog-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="edit-track-title" className="report-dialog">
      <h2 id="edit-track-title">Edit track</h2><form onSubmit={(event) => { event.preventDefault(); editMutation.mutate() }}>
        <label className="field"><span>Title</span><input required maxLength={120} value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
        <label className="field"><span>Artist name</span><input required maxLength={120} value={artist} onChange={(event) => setArtist(event.currentTarget.value)} /></label>
        <label className="field"><span>Category</span><select value={category} onChange={(event) => setCategory(event.currentTarget.value)}>{categories.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="field"><span>Visibility</span><select value={visibility} onChange={(event) => setVisibility(event.currentTarget.value as Track['visibility'])}><option>PUBLIC</option><option>FOLLOWERS</option><option>PRIVATE</option></select></label>
        <label><input type="checkbox" checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.currentTarget.checked)} /> I own this audio or have permission to share it</label>
        <button className="button button--primary" type="submit" disabled={!rightsConfirmed || editMutation.isPending}>Save</button><button className="button button--outline" type="button" onClick={() => setEditing(null)}>Cancel</button>
      </form>
    </section></div>}
    {deleting && <div className="report-dialog-backdrop"><section role="alertdialog" aria-modal="true" aria-labelledby="delete-track-title" className="report-dialog">
      <h2 id="delete-track-title">Delete track?</h2><p>This will permanently delete “{deleting.title}”.</p><button className="button button--quiet" type="button" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate(deleting)}>Delete</button><button className="button button--outline" type="button" onClick={() => setDeleting(null)}>Cancel</button>
    </section></div>}
  </section>
}

export function PlaylistDetailPage() {
  const { playlistId = '' } = useParams()
  const queryClient = useQueryClient()
  const player = useMusicPlayer()
  const { user } = useAuth()
  const playlistQuery = useQuery({
    queryKey: ['music', 'playlist', playlistId],
    queryFn: () => apiRequest<PlaylistDetail>(`/api/v1/playlists/${playlistId}`),
    enabled: Boolean(playlistId),
  })
  const tracks = playlistQuery.data?.tracks ?? []
  const canManage = playlistQuery.data?.owner_id === user?.id
  const updateOrder = useMutation({
    mutationFn: (next: Track[]) => apiRequest(`/api/v1/playlists/${playlistId}/order`, { method: 'PUT', body: { track_ids: next.map((track) => track.id) } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['music', 'playlist', playlistId] }),
  })
  const removeTrack = useMutation({
    mutationFn: (trackId: string) => apiRequest(`/api/v1/playlists/${playlistId}/tracks/${trackId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['music', 'playlist', playlistId] }),
  })
  if (playlistQuery.isPending) return <p role="status">Loading playlist…</p>
  if (playlistQuery.isError) return <div className="page-state page-state--error" role="alert"><h1>{playlistQuery.error instanceof ApiError && playlistQuery.error.status === 404 ? 'Playlist not found' : 'Playlist unavailable'}</h1><p>{getFriendlyErrorMessage(playlistQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void playlistQuery.refetch()}>Retry</button></div>
  return <main className="page-stack" data-section="music"><header className="page-heading-row"><div><span className="eyebrow">PLAYLIST</span><h1>{playlistQuery.data.title}</h1></div><button className="button button--primary" type="button" disabled={!tracks.length} onClick={() => void player.playQueue(tracks, 0)}>Play all</button></header>
    {(updateOrder.isError || removeTrack.isError) && <p className="form-alert" role="alert">{getFriendlyErrorMessage(updateOrder.error ?? removeTrack.error)}</p>}
    {tracks.length === 0 ? <p>This playlist has no playable tracks yet.</p> : <ol className="learning-section">{tracks.map((track, index) => <li className="playlist-track-row" key={track.id}>
      <Link to={`/music/tracks/${track.id}`}>{track.title}</Link><span>{track.artist_name}</span>
      <button className="button button--outline" type="button" onClick={() => void player.playQueue(tracks, index)}>Play</button>
      {canManage && <><button className="button button--outline" type="button" aria-label={`Move ${track.title} up`} disabled={index === 0 || updateOrder.isPending} onClick={() => updateOrder.mutate([...tracks.slice(0, index - 1), tracks[index], tracks[index - 1], ...tracks.slice(index + 1)])}>Move up</button>
      <button className="button button--outline" type="button" aria-label={`Move ${track.title} down`} disabled={index === tracks.length - 1 || updateOrder.isPending} onClick={() => updateOrder.mutate([...tracks.slice(0, index), tracks[index + 1], tracks[index], ...tracks.slice(index + 2)])}>Move down</button>
      <button className="button button--quiet" type="button" disabled={removeTrack.isPending} onClick={() => removeTrack.mutate(track.id)}>Remove</button></>}
    </li>)}</ol>}
  </main>
}

export function TrackDetailPage() {
  const { trackId = '' } = useParams()
  const player = useMusicPlayer()
  const { user } = useAuth()
  const trackQuery = useQuery({
    queryKey: ['music', 'track', trackId],
    queryFn: () => apiRequest<Track>(`/api/v1/tracks/${trackId}`),
    enabled: Boolean(trackId),
  })
  const mediaQuery = useQuery({
    queryKey: ['media', trackQuery.data?.media_asset_id],
    queryFn: () => apiRequest<{ download_url: string }>(`/api/v1/media/${trackQuery.data?.media_asset_id}/download`),
    enabled: Boolean(trackQuery.data?.media_asset_id),
  })
  if (trackQuery.isPending) return <p role="status">Loading track…</p>
  if (trackQuery.isError) return <div className="page-state page-state--error" role="alert"><h1>{trackQuery.error instanceof ApiError && trackQuery.error.status === 404 ? 'Track not found' : 'Track unavailable'}</h1><p>{getFriendlyErrorMessage(trackQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void trackQuery.refetch()}>Retry</button></div>
  const track = trackQuery.data
  return <article className="page-stack" data-section="music">
    <header className="page-heading-row"><div><span className="eyebrow">COMMUNITY MUSIC</span><h1>{track.title}</h1><p>{track.artist_name} · {track.category}</p></div><button className="button button--primary" type="button" onClick={() => void player.playQueue([track], 0)}>Play</button></header>
    <p>Shared by <Link to={`/users/${track.owner_id}`}>{track.owner_id}</Link> · {track.play_count} plays</p>
    <p className="learning-section">This is user-uploaded audio. The uploader confirms they own this audio or have permission to share it. No commercial catalogue streaming.</p>
    {mediaQuery.isPending ? <p role="status">Loading audio…</p> : mediaQuery.isError ? <div role="alert" className="inline-error"><p>{getFriendlyErrorMessage(mediaQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void mediaQuery.refetch()}>Retry</button></div> : <audio controls src={mediaQuery.data.download_url} aria-label={`Play ${track.title}`} />}
    {track.owner_id !== user?.id && <ReportDialog targetType="TRACK" targetId={track.id} />}
  </article>
}
