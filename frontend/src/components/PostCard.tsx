import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Heart, LoaderCircle, MessageCircle, Trash2 } from 'lucide-react'
import { deletePost, getPostEngagement, setPostLike, type Post } from '../api/social'
import { getFriendlyErrorMessage } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { CommentsSection } from './CommentsSection'
import { relativeTime, updateOptimisticLike, type Engagement } from './feedHelpers'
import { UserIdentity } from './UserIdentity'

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
  const engagementKey = ['engagement', post.id]
  const engagementQuery = useQuery({
    queryKey: engagementKey,
    queryFn: () => getPostEngagement(post.id),
  })
  const likeMutation = useMutation({
    mutationFn: (liked: boolean) => setPostLike(post.id, liked),
    onMutate: async (liked) => {
      await queryClient.cancelQueries({ queryKey: engagementKey })
      const previous = queryClient.getQueryData<Engagement>(engagementKey)
      queryClient.setQueryData<Engagement>(
        engagementKey,
        updateOptimisticLike(previous, user!.id, liked),
      )
      return { previous }
    },
    onError: (_error, _liked, context) => {
      if (context?.previous) queryClient.setQueryData(engagementKey, context.previous)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: engagementKey }),
  })
  const deleteMutation = useMutation({
    mutationFn: () => deletePost(post.id),
    onSuccess: () => onDeleted(post.id),
  })

  const engagement = engagementQuery.data
  const isLiked = Boolean(user && engagement?.likedByUserIds.has(user.id))

  return (
    <article className="post-card" aria-label={`Post by ${post.author.username}`}>
      <div className="post-card__header">
        <UserIdentity userId={post.author_id} username={post.author.username} currentUserId={user?.id ?? ''} />
        <time dateTime={post.created_at}>{relativeTime(post.created_at)}</time>
        {post.author_id === user?.id && (
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
        )}
      </div>
      <p className="post-card__content">{post.content}</p>
      <div className="post-card__actions">
        <button
          className={`post-action${isLiked ? ' post-action--liked' : ''}`}
          type="button"
          aria-pressed={isLiked}
          aria-label={isLiked ? `Unlike post, ${engagement?.likeCount ?? 0} likes` : `Like post, ${engagement?.likeCount ?? 0} likes`}
          disabled={engagementQuery.isPending || likeMutation.isPending || engagementQuery.isError}
          onClick={() => likeMutation.mutate(!isLiked)}
        >
          <Heart size={17} fill={isLiked ? 'currentColor' : 'none'} aria-hidden="true" />
          <span>{engagementQuery.isPending ? '…' : engagement?.likeCount ?? 0}</span>
        </button>
        <button
          className={`post-action${commentsOpen ? ' post-action--active' : ''}`}
          type="button"
          aria-expanded={commentsOpen}
          aria-label={`${commentsOpen ? 'Hide' : 'Show'} comments, ${engagement?.commentCount ?? 0} comments`}
          onClick={() => setCommentsOpen((open) => !open)}
        >
          <MessageCircle size={17} aria-hidden="true" />
          <span>{engagement?.commentCount ?? 0}</span>
        </button>
        {engagementQuery.isError && (
          <button className="post-action post-action--retry" type="button" onClick={() => void engagementQuery.refetch()}>Retry counts</button>
        )}
      </div>
      {likeMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(likeMutation.error)}</p>}
      {deleteMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(deleteMutation.error)}</p>}
      {commentsOpen && user && (
        <CommentsSection
          postId={post.id}
          currentUserId={user.id}
          onCommentsChanged={() => { void queryClient.invalidateQueries({ queryKey: engagementKey }) }}
        />
      )}
    </article>
  )
}