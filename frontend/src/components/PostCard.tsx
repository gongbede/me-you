import { useState } from 'react'
import { useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { Heart, LoaderCircle, MessageCircle, Trash2 } from 'lucide-react'
import { deletePost, setPostLike, type FeedPage, type Post } from '../api/social'
import { getFriendlyErrorMessage } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { CommentsSection } from './CommentsSection'
import { relativeTime, updateOptimisticLike } from './feedHelpers'
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

  const isLiked = post.liked_by_me

  return (
    <article className="post-card" aria-label={`Post by ${post.author.username}`}>
      <div className="post-card__header">
        <UserIdentity
          userId={post.author_id}
          username={post.author.username}
          displayName={post.author.display_name}
          avatarUrl={post.author.avatar_url}
          currentUserId={user?.id ?? ''}
        />
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
      </div>
      {likeMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(likeMutation.error)}</p>}
      {deleteMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(deleteMutation.error)}</p>}
      {commentsOpen && user && (
        <CommentsSection
          postId={post.id}
          currentUserId={user.id}
          onCommentsChanged={() => { void queryClient.invalidateQueries({ queryKey: feedKey }) }}
        />
      )}
    </article>
  )
}