import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ApiError, apiRequest, getFriendlyErrorMessage } from '../api/client'
import { ReportDialog } from '../components/ReportDialog'
import { useAuth } from '../hooks/useAuth'

type Video = {
  id: string
  owner_id: string
  media_asset_id: string
  title: string
  description: string
  category: string
  visibility: 'PUBLIC' | 'FOLLOWERS' | 'PRIVATE'
  view_count: number
  like_count: number
  liked_by_me: boolean
}
type VideoComment = { id: string; video_id: string; author_id: string; content: string; created_at: string }

export function VideoWatchPage() {
  const { videoId = '' } = useParams()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const countedRef = useRef('')
  const [content, setContent] = useState('')
  const [viewError, setViewError] = useState('')
  const videoQuery = useQuery({
    queryKey: ['videos', videoId],
    queryFn: () => apiRequest<Video>(`/api/v1/videos/${videoId}`),
    enabled: Boolean(videoId),
  })
  const mediaQuery = useQuery({
    queryKey: ['media', videoQuery.data?.media_asset_id],
    queryFn: () => apiRequest<{ download_url: string }>(`/api/v1/media/${videoQuery.data?.media_asset_id}/download`),
    enabled: Boolean(videoQuery.data?.media_asset_id),
  })
  const commentsQuery = useQuery({
    queryKey: ['video-comments', videoId],
    queryFn: () => apiRequest<VideoComment[]>(`/api/v1/videos/${videoId}/comments?limit=100`),
    enabled: Boolean(videoId && videoQuery.data),
  })
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['videos', videoId] }),
      queryClient.invalidateQueries({ queryKey: ['video-comments', videoId] }),
    ])
  }
  const likeMutation = useMutation({
    mutationFn: (liked: boolean) => apiRequest(`/api/v1/videos/${videoId}/like`, { method: liked ? 'DELETE' : 'POST' }),
    onSuccess: refresh,
  })
  const commentMutation = useMutation({
    mutationFn: (value: string) => apiRequest(`/api/v1/videos/${videoId}/comments`, { method: 'POST', body: { content: value } }),
    onSuccess: async () => { setContent(''); await refresh() },
  })
  const deleteCommentMutation = useMutation({
    mutationFn: (commentId: string) => apiRequest(`/api/v1/videos/comments/${commentId}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })

  useEffect(() => {
    if (!videoQuery.data || countedRef.current === videoId) return
    countedRef.current = videoId
    void apiRequest(`/api/v1/videos/${videoId}/view`, { method: 'POST' })
      .then(() => queryClient.invalidateQueries({ queryKey: ['videos', videoId] }))
      .catch((error: unknown) => setViewError(getFriendlyErrorMessage(error)))
  }, [queryClient, videoId, videoQuery.data])

  if (videoQuery.isPending) return <p className="learning-loading" role="status">Loading video…</p>
  if (videoQuery.isError) return <div className="page-state page-state--error" role="alert"><h1>{videoQuery.error instanceof ApiError && videoQuery.error.status === 404 ? 'Video not found' : 'Video unavailable'}</h1><p>{getFriendlyErrorMessage(videoQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void videoQuery.refetch()}>Retry</button></div>

  const video = videoQuery.data
  function submitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (content.trim()) commentMutation.mutate(content.trim())
  }

  return <article className="page-stack video-watch-page" data-section="videos">
    {mediaQuery.isPending ? <p role="status">Loading video player…</p> : mediaQuery.isError ? <div role="alert" className="inline-error"><p>{getFriendlyErrorMessage(mediaQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void mediaQuery.refetch()}>Retry</button></div> : <video className="video-watch-player" src={mediaQuery.data.download_url} controls playsInline aria-label={video.title} />}
    <header><h1>{video.title}</h1><p>{video.description}</p><p><Link to={`/users/${video.owner_id}`}>View creator profile</Link> · {video.view_count} views · {video.visibility}</p></header>
    <div className="video-watch-actions">
      <button className="button button--outline" type="button" onClick={() => likeMutation.mutate(video.liked_by_me)} disabled={likeMutation.isPending}>{video.liked_by_me ? 'Unlike' : 'Like'} · {video.like_count}</button>
      {video.owner_id !== user?.id && <ReportDialog targetType="VIDEO" targetId={video.id} />}
    </div>
    {viewError && <p role="alert" className="form-alert">{viewError}</p>}
    {likeMutation.isError && <p role="alert" className="form-alert">{getFriendlyErrorMessage(likeMutation.error)}</p>}
    <section className="learning-section" aria-label="Video comments">
      <h2>Comments</h2>
      {commentsQuery.isPending ? <p role="status">Loading comments…</p> : commentsQuery.isError ? <div role="alert" className="inline-error"><p>{getFriendlyErrorMessage(commentsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void commentsQuery.refetch()}>Retry</button></div> : commentsQuery.data.length === 0 ? <p>No comments yet.</p> : <ul>{commentsQuery.data.map((comment) => <li key={comment.id}><p>{comment.content}</p><small>{comment.author_id}</small>{comment.author_id === user?.id && <button className="button button--quiet" type="button" disabled={deleteCommentMutation.isPending} onClick={() => deleteCommentMutation.mutate(comment.id)}>Delete</button>}</li>)}</ul>}
      <form onSubmit={submitComment}><label className="field"><span>Add a comment</span><textarea rows={3} maxLength={2000} value={content} onChange={(event) => setContent(event.currentTarget.value)} /></label><button className="button button--primary" type="submit" disabled={!content.trim() || commentMutation.isPending}>Comment</button></form>
      {(commentMutation.isError || deleteCommentMutation.isError) && <p role="alert" className="form-alert">{getFriendlyErrorMessage(commentMutation.error ?? deleteCommentMutation.error)}</p>}
    </section>
  </article>
}
