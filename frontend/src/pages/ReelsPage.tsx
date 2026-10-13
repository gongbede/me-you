import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { ArrowDown, Heart, LoaderCircle, MessageCircle, Pause, Play, Plus, Trash2, Volume2, VolumeX, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, getFriendlyErrorMessage } from '../api/client'
import { setPostLike, type Post } from '../api/social'
import { CommentsSection } from '../components/CommentsSection'
import { UserIdentity } from '../components/UserIdentity'
import { useAuth } from '../hooks/useAuth'
import { deleteReel, getReelLimits, getReelsPage, uploadReel, validateReelFile, type Reel, type ReelFeedPage } from '../api/reels'

const reelFeedKey = ['reels', 'feed'] as const

function reducedMotionPreferred() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function updateReelLike(
  current: InfiniteData<ReelFeedPage> | undefined,
  reelId: string,
  liked: boolean,
): InfiniteData<ReelFeedPage> | undefined {
  if (!current) return current
  return {
    ...current,
    pages: current.pages.map((page) => ({
      ...page,
      items: page.items.map((reel) => reel.id === reelId ? {
        ...reel,
        liked_by_me: liked,
        like_count: Math.max(0, reel.like_count + (liked ? 1 : -1)),
      } : reel),
    })),
  }
}

function ReelUploadForm({
  limits,
  onCreated,
}: {
  limits: Awaited<ReturnType<typeof getReelLimits>>
  onCreated: (reel: Reel) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [caption, setCaption] = useState('')
  const [fileError, setFileError] = useState('')
  const [durationWarning, setDurationWarning] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error('Choose a video first.')
      return uploadReel(file, caption, limits, setProgress)
    },
    onSuccess: (reel) => {
      setFile(null)
      setCaption('')
      setFileError('')
      setDurationWarning(false)
      setProgress(null)
      onCreated(reel)
    },
    onError: () => setProgress(null),
  })

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    setDurationWarning(false)
    return () => URL.revokeObjectURL(url)
  }, [file])

  function selectFile(event: React.ChangeEvent<HTMLInputElement>) {
    const nextFile = event.currentTarget.files?.[0] ?? null
    setFileError(nextFile ? validateReelFile(nextFile, limits) ?? '' : '')
    setFile(nextFile)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setProgress(0)
    uploadMutation.mutate()
  }

  return (
    <form className="reel-upload-form" onSubmit={submit}>
      <label className="field"><span>Video</span><input type="file" accept={limits.content_types.join(',')} onChange={selectFile} disabled={uploadMutation.isPending} /></label>
      <p className="reel-upload-hint">MP4 or WebM · up to {Math.floor(limits.max_bytes / 1_000_000)} MB</p>
      {fileError && <p className="form-alert" role="alert">{fileError}</p>}
      {previewUrl && <div className="reel-upload-preview">
        <video ref={videoRef} src={previewUrl} controls muted playsInline preload="metadata" aria-label="Selected video preview" onLoadedMetadata={() => setDurationWarning((videoRef.current?.duration ?? 0) > 60)} />
        {durationWarning && <p className="form-alert" role="status">This video is longer than 60 seconds. Reels do not enforce a duration limit yet.</p>}
      </div>}
      <label className="field"><span>Caption</span><textarea rows={3} maxLength={10_000} required value={caption} onChange={(event) => setCaption(event.currentTarget.value)} placeholder="Write a caption…" /></label>
      <span className="reel-caption-count">{caption.length}/10,000</span>
      {progress !== null && uploadMutation.isPending && <div className="reel-upload-progress" role="status" aria-live="polite"><span>Uploading and processing metadata… {progress}%</span><progress aria-label="Video upload progress" max={100} value={progress} /></div>}
      {uploadMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(uploadMutation.error)}</p>}
      <button className="button button--primary" type="submit" disabled={!file || Boolean(fileError) || !caption.trim() || uploadMutation.isPending}><Plus size={16} aria-hidden="true" />{uploadMutation.isPending ? 'Publishing…' : 'Publish Reel'}</button>
    </form>
  )
}

function ReelSlide({
  reel,
  root,
  active,
  reducedMotion,
  currentUserId,
  onVisibility,
  onDeleted,
}: {
  reel: Reel
  root: HTMLDivElement | null
  active: boolean
  reducedMotion: boolean
  currentUserId: string
  onVisibility: (reelId: string, visible: boolean) => void
  onDeleted: (reelId: string) => void
}) {
  const queryClient = useQueryClient()
  const videoRef = useRef<HTMLVideoElement>(null)
  const slideRef = useRef<HTMLElement>(null)
  const [muted, setMuted] = useState(true)
  const [playing, setPlaying] = useState(false)
  const [commentsOpen, setCommentsOpen] = useState(false)
  const likeMutation = useMutation({
    mutationFn: (liked: boolean) => setPostLike(reel.id, liked),
    onMutate: async (liked) => {
      await queryClient.cancelQueries({ queryKey: reelFeedKey })
      const previous = queryClient.getQueryData<InfiniteData<ReelFeedPage>>(reelFeedKey)
      queryClient.setQueryData(reelFeedKey, (current: InfiniteData<ReelFeedPage> | undefined) => updateReelLike(current, reel.id, liked))
      return { previous }
    },
    onError: (_error, _liked, context) => {
      if (context?.previous) queryClient.setQueryData(reelFeedKey, context.previous)
    },
  })
  const deleteMutation = useMutation({
    mutationFn: () => deleteReel(reel.id),
    onSuccess: () => onDeleted(reel.id),
  })

  useEffect(() => {
    const element = slideRef.current
    if (!element || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(([entry]) => {
      onVisibility(reel.id, entry.isIntersecting && entry.intersectionRatio >= 0.65)
    }, { root, threshold: [0, 0.65, 1] })
    observer.observe(element)
    return () => observer.disconnect()
  }, [onVisibility, reel.id, root])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (active && !reducedMotion) {
      video.muted = true
      setMuted(true)
      void video.play().catch(() => setPlaying(false))
    } else {
      video.pause()
    }
  }, [active, reducedMotion])

  function togglePlayback() {
    const video = videoRef.current
    if (!video) return
    if (video.paused) void video.play().catch(() => setPlaying(false))
    else video.pause()
  }

  function toggleMuted() {
    const video = videoRef.current
    if (!video) return
    video.muted = !muted
    setMuted(video.muted)
  }

  function deleteOwnReel() {
    if (window.confirm('Delete this Reel and its video?')) deleteMutation.mutate()
  }

  return (
    <article className="reel-slide" ref={slideRef} aria-label={`Reel by ${reel.author.username}`}>
      {reel.video_url ? <video ref={videoRef} className="reel-slide__video" src={reel.video_url} muted={muted} loop playsInline preload="metadata" aria-label={`Reel video by ${reel.author.username}`} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onClick={togglePlayback} /> : <div className="reel-slide__video reel-slide__video--error" role="alert">Video unavailable</div>}
      <div className="reel-slide__scrim" aria-hidden="true" />
      <button className="reel-play-toggle" type="button" aria-label={playing ? 'Pause Reel' : 'Play Reel'} aria-pressed={playing} onClick={togglePlayback}>{playing ? <Pause size={24} fill="currentColor" aria-hidden="true" /> : <Play size={24} fill="currentColor" aria-hidden="true" />}</button>
      <button className="reel-mute-toggle" type="button" aria-label={muted ? 'Unmute Reel' : 'Mute Reel'} aria-pressed={!muted} onClick={toggleMuted}>{muted ? <VolumeX size={20} aria-hidden="true" /> : <Volume2 size={20} aria-hidden="true" />}</button>
      <aside className="reel-slide__actions" aria-label="Reel actions">
        <button className={`reel-action${reel.liked_by_me ? ' is-liked' : ''}`} type="button" aria-pressed={reel.liked_by_me} aria-label={`${reel.liked_by_me ? 'Unlike' : 'Like'} Reel, ${reel.like_count} likes`} disabled={likeMutation.isPending} onClick={() => likeMutation.mutate(!reel.liked_by_me)}><Heart size={22} fill={reel.liked_by_me ? 'currentColor' : 'none'} aria-hidden="true" /><span>{reel.like_count}</span></button>
        <button className="reel-action" type="button" aria-expanded={commentsOpen} aria-label={`Comments, ${reel.comment_count}`} onClick={() => setCommentsOpen(true)}><MessageCircle size={22} aria-hidden="true" /><span>{reel.comment_count}</span></button>
        {reel.author_id === currentUserId && <button className="reel-action" type="button" aria-label="Delete Reel" onClick={deleteOwnReel}><Trash2 size={20} aria-hidden="true" /></button>}
      </aside>
      <div className="reel-slide__caption">
        <Link to={`/users/${reel.author_id}`} className="reel-author"><UserIdentity userId={reel.author_id} username={reel.author.username} displayName={reel.author.display_name} avatarUrl={reel.author.avatar_url} currentUserId={currentUserId} compact /></Link>
        <p>{reel.content}</p>
        {likeMutation.isError && <p className="reel-error" role="alert">{getFriendlyErrorMessage(likeMutation.error)}</p>}
        {deleteMutation.isError && <p className="reel-error" role="alert">{getFriendlyErrorMessage(deleteMutation.error)}</p>}
      </div>
      {commentsOpen && <div className="reel-comments-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) setCommentsOpen(false) }}>
        <section className="reel-comments-drawer" role="dialog" aria-modal="true" aria-label="Reel comments">
          <header><h2>Comments</h2><button className="icon-button" type="button" aria-label="Close comments" onClick={() => setCommentsOpen(false)}><X size={19} aria-hidden="true" /></button></header>
          <CommentsSection postId={reel.id} currentUserId={currentUserId} onCommentsChanged={() => { void queryClient.invalidateQueries({ queryKey: reelFeedKey }) }} />
        </section>
      </div>}
    </article>
  )
}

export function ReelsViewer({ embedded = false }: { embedded?: boolean }) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const limitsQuery = useQuery({ queryKey: ['reels', 'limits'], queryFn: getReelLimits })
  const reelsQuery = useInfiniteQuery({
    queryKey: reelFeedKey,
    queryFn: ({ pageParam }) => getReelsPage(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
  const [activeId, setActiveId] = useState<string | null>(null)
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(reducedMotionPreferred)
  const viewerRef = useRef<HTMLDivElement>(null)
  const loadMoreRef = useRef<HTMLDivElement>(null)
  const reels: Reel[] = reelsQuery.data?.pages.flatMap((page) => page.items) ?? []

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReducedMotion(media.matches)
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])

  useEffect(() => {
    const sentinel = loadMoreRef.current
    const root = viewerRef.current
    if (!sentinel || !root || !reelsQuery.hasNextPage || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting) && !reelsQuery.isFetchingNextPage) {
        void reelsQuery.fetchNextPage()
      }
    }, { root, rootMargin: '240px 0px', threshold: 0 })
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [reelsQuery.fetchNextPage, reelsQuery.hasNextPage, reelsQuery.isFetchingNextPage, reels.length])

  function handleVisibility(reelId: string, isVisible: boolean) {
    setActiveId((current) => isVisible ? reelId : current === reelId ? null : current)
  }

  function removeReel(reelId: string) {
    queryClient.setQueryData<InfiniteData<ReelFeedPage>>(reelFeedKey, (current) => current && ({
      ...current,
      pages: current.pages.map((page) => ({ ...page, items: page.items.filter((reel) => reel.id !== reelId) })),
    }))
    void queryClient.invalidateQueries({ queryKey: reelFeedKey })
  }

  function createdReel(reel: Reel) {
    void queryClient.invalidateQueries({ queryKey: reelFeedKey })
    setIsUploadOpen(false)
    setActiveId(reel.id)
  }

  return (
    <section className={`reels-shell${embedded ? ' reels-shell--embedded' : ''}`} aria-label="Reels">
      <header className="reels-heading"><div><span className="learning-kicker">SHORT VIDEOS</span><h1>Reels</h1></div><button className="button button--primary" type="button" onClick={() => setIsUploadOpen((open) => !open)} aria-expanded={isUploadOpen}><Plus size={16} aria-hidden="true" />{isUploadOpen ? 'Close upload' : 'Create Reel'}</button></header>
      {isUploadOpen && <section className="learning-section reel-upload-panel" aria-label="Create a Reel">
        {limitsQuery.isPending ? <p className="learning-loading" role="status">Loading video limits…</p> : limitsQuery.isError ? <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(limitsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void limitsQuery.refetch()}>Retry</button></div> : <ReelUploadForm limits={limitsQuery.data} onCreated={createdReel} />}
      </section>}
      {reelsQuery.isPending ? <div className="page-state" role="status">Loading Reels…</div> : reelsQuery.isError && !reelsQuery.data ? <div className="page-state page-state--error" role="alert"><h2>Reels unavailable</h2><p>{getFriendlyErrorMessage(reelsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void reelsQuery.refetch()}>Retry</button></div> : reels.length === 0 ? <div className="reels-empty"><MessageCircle size={25} aria-hidden="true" /><h2>No Reels yet</h2><p>Follow people who share video, or publish your first Reel.</p></div> : <>
        <div className="reels-viewer" ref={viewerRef} aria-label="Reel viewer">
          {reels.map((reel) => <ReelSlide key={reel.id} reel={reel} root={viewerRef.current} active={activeId === reel.id} reducedMotion={reducedMotion} currentUserId={user?.id ?? ''} onVisibility={handleVisibility} onDeleted={removeReel} />)}
          <div ref={loadMoreRef} className="reels-load-sentinel" aria-hidden="true" />
        </div>
        {reelsQuery.hasNextPage && <button className="button button--outline reels-load-more" type="button" disabled={reelsQuery.isFetchingNextPage} onClick={() => void reelsQuery.fetchNextPage()}>{reelsQuery.isFetchingNextPage && <LoaderCircle size={16} className="spin" aria-hidden="true" />}{reelsQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}</button>}
        {reelsQuery.isFetchNextPageError && <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(reelsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void reelsQuery.fetchNextPage()}>Retry</button></div>}
      </>}
    </section>
  )
}

export function ReelsPage() {
  return <div className="page-stack reels-page"><ReelsViewer /></div>
}