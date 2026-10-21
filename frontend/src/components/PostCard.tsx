import { useEffect, useState } from 'react'
import { useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { Check, Copy, Heart, LoaderCircle, MessageCircle, Pencil, Trash2, X } from 'lucide-react'
import { deletePost, setPostLike, updatePost, type FeedPage, type Post } from '../api/social'
import { getFriendlyErrorMessage } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { CommentsSection } from './CommentsSection'
import { relativeTime, updateOptimisticLike } from './feedHelpers'
import { UserIdentity } from './UserIdentity'
import { ReportDialog } from './ReportDialog'

export function PostCard({
  post,
  onDeleted,
}: {
  post: Post
  onDeleted: (postId: string) => void
}) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [commentsOpen, setCommentsOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draftContent, setDraftContent] = useState(post.content)
  const [displayContent, setDisplayContent] = useState(post.content)
  const [isEdited, setIsEdited] = useState(post.edited)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [copyMessage, setCopyMessage] = useState<string | null>(null)
  const feedKey = ['feed'] as const
  const likeMutation = useMutation({
    mutationFn: (liked: boolean) => setPostLike(post.id, liked),
    onMutate: async (liked) => {
      await queryClient.cancelQueries({ queryKey: feedKey })
      const previous = queryClient.getQueryData<InfiniteData<FeedPage>>(feedKey)
      queryClient.setQueryData<InfiniteData<FeedPage>>(
        feedKey,
        (current) => updateOptimisticLike(current, post.id, liked),
      )
      return { previous }
    },
    onError: (_error, _liked, context) => {
      if (context?.previous) queryClient.setQueryData(feedKey, context.previous)
    },
  })
  const deleteMutation = useMutation({
    mutationFn: () => deletePost(post.id),
    onSuccess: () => onDeleted(post.id),
  })
  const editMutation = useMutation({
    mutationFn: () => updatePost(post.id, { content: draftContent.trim() }),
    onSuccess: (updatedPost) => {
      queryClient.setQueryData<InfiniteData<FeedPage>>(feedKey, (current) => current && ({
        ...current,
        pages: current.pages.map((page) => ({
          ...page,
          items: page.items.map((item) => item.id === post.id ? updatedPost : item),
        })),
      }))
      setDisplayContent(updatedPost.content)
      setIsEdited(updatedPost.edited)
      setEditing(false)
    },
  })

  const isLiked = post.liked_by_me

  useEffect(() => {
    if (lightboxIndex === null) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setLightboxIndex(null)
      if (event.key === 'ArrowLeft') {
        setLightboxIndex((current) => current === null ? null : (current + post.attachments!.length - 1) % post.attachments!.length)
      }
      if (event.key === 'ArrowRight') {
        setLightboxIndex((current) => current === null ? null : (current + 1) % post.attachments!.length)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [lightboxIndex, post.attachments])

  async function copyLink() {
    try {
      const url = new URL(window.location.href)
      url.hash = `post-${post.id}`
      await navigator.clipboard.writeText(url.toString())
      setCopyMessage('Link copied')
    } catch {
      setCopyMessage('Could not copy link')
    }
  }

  return (
    <article id={`post-${post.id}`} className="post-card" aria-label={`Post by ${post.author.username}`}>
      <div className="post-card__header">
        <UserIdentity
          userId={post.author_id}
          username={post.author.username}
          displayName={post.author.display_name}
          avatarUrl={post.author.avatar_url}
          currentUserId={user?.id ?? ''}
        />
        <time dateTime={post.created_at}>{relativeTime(post.created_at)}</time>
        {post.author_id !== user?.id && <ReportDialog targetType={post.post_type === 'REEL' ? 'REEL' : 'POST'} targetId={post.id} />}
        {post.author_id === user?.id && (
          <>
            {post.post_type === 'POST' && <button className="icon-button" type="button" aria-label="Edit post" title="Edit post" onClick={() => { setDraftContent(post.content); setEditing(true) }}><Pencil size={16} aria-hidden="true" /></button>}
            <button
              className="icon-button"
              type="button"
              aria-label="Delete post"
              title="Delete post"
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (window.confirm('Delete this post?')) deleteMutation.mutate()
              }}
            >
              {deleteMutation.isPending ? <LoaderCircle size={17} className="spin" /> : <Trash2 size={17} aria-hidden="true" />}
            </button>
          </>
        )}
      </div>
      {editing ? (
        <form className="post-edit-form" onSubmit={(event) => { event.preventDefault(); editMutation.mutate() }}>
          <label className="sr-only" htmlFor={`edit-post-${post.id}`}>Edit post</label>
          <textarea id={`edit-post-${post.id}`} value={draftContent} maxLength={10_000} onChange={(event) => setDraftContent(event.currentTarget.value)} />
          <div className="post-edit-form__actions">
            <span>{Array.from(draftContent).length}/10,000</span>
            <button className="icon-button" type="button" aria-label="Cancel edit" title="Cancel edit" onClick={() => setEditing(false)}><X size={16} aria-hidden="true" /></button>
            <button className="button button--primary" type="submit" disabled={!draftContent.trim() || editMutation.isPending}>
              {editMutation.isPending ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : <Check size={16} aria-hidden="true" />} Save
            </button>
          </div>
          {editMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(editMutation.error)}</p>}
        </form>
      ) : (
        <>
          <p className="post-card__content">{displayContent}</p>
          {isEdited && <span className="post-card__edited">Edited</span>}
        </>
      )}
      {post.attachments?.length ? (
        <div className={`post-image-grid post-image-grid--${Math.min(post.attachments.length, 4)}`}>
          {post.attachments.map((attachment, index) => (
            <button
              className="post-image-grid__item"
              key={attachment.id}
              type="button"
              aria-label={`Open image ${index + 1} of ${post.attachments!.length}`}
              onClick={() => setLightboxIndex(index)}
            >
              <img src={attachment.image_url} alt={attachment.alt_text} loading="lazy" />
            </button>
          ))}
        </div>
      ) : null}
      <div className="post-card__actions">
        <button
          className={`post-action${isLiked ? ' post-action--liked' : ''}`}
          type="button"
          aria-pressed={isLiked}
          aria-label={isLiked ? `Unlike post, ${post.like_count} likes` : `Like post, ${post.like_count} likes`}
          disabled={likeMutation.isPending}
          onClick={() => likeMutation.mutate(!isLiked)}
        >
          <Heart size={17} fill={isLiked ? 'currentColor' : 'none'} aria-hidden="true" />
          <span>{post.like_count}</span>
        </button>
        <button
          className={`post-action${commentsOpen ? ' post-action--active' : ''}`}
          type="button"
          aria-expanded={commentsOpen}
          aria-label={`${commentsOpen ? 'Hide' : 'Show'} comments, ${post.comment_count} comments`}
          onClick={() => setCommentsOpen((open) => !open)}
        >
          <MessageCircle size={17} aria-hidden="true" />
          <span>{post.comment_count}</span>
        </button>
        <button className="post-action post-action--copy" type="button" aria-label="Copy post link" title="Copy post link" onClick={() => void copyLink()}>
          <Copy size={16} aria-hidden="true" />
        </button>
      </div>
      {copyMessage && <span className="sr-only" role="status">{copyMessage}</span>}
      {likeMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(likeMutation.error)}</p>}
      {deleteMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(deleteMutation.error)}</p>}
      {commentsOpen && user && (
        <CommentsSection
          postId={post.id}
          currentUserId={user.id}
          onCommentsChanged={() => { void queryClient.invalidateQueries({ queryKey: feedKey }) }}
        />
      )}
      {lightboxIndex !== null && post.attachments?.[lightboxIndex] && (
        <div className="post-lightbox" role="presentation" onClick={() => setLightboxIndex(null)}>
          <section className="post-lightbox__dialog" role="dialog" aria-modal="true" aria-label="Post image viewer" onClick={(event) => event.stopPropagation()}>
            <button className="icon-button post-lightbox__close" type="button" aria-label="Close image viewer" title="Close" onClick={() => setLightboxIndex(null)}><X size={20} aria-hidden="true" /></button>
            <img src={post.attachments[lightboxIndex].image_url} alt={post.attachments[lightboxIndex].alt_text} />
            {post.attachments.length > 1 && <>
              <button className="icon-button post-lightbox__previous" type="button" aria-label="Previous image" onClick={() => setLightboxIndex((lightboxIndex + post.attachments!.length - 1) % post.attachments!.length)}>‹</button>
              <button className="icon-button post-lightbox__next" type="button" aria-label="Next image" onClick={() => setLightboxIndex((lightboxIndex + 1) % post.attachments!.length)}>›</button>
              <span className="post-lightbox__count">{lightboxIndex + 1} / {post.attachments.length}</span>
            </>}
          </section>
        </div>
      )}
    </article>
  )
}