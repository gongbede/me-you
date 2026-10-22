import { useState, type FormEvent } from 'react'
import { useInfiniteQuery, useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { Check, Heart, LoaderCircle, MessageCircle, Pencil, Send, Trash2, X } from 'lucide-react'
import { createComment, deleteComment, getCommentsPage, setCommentLike, updateComment, type Comment } from '../api/social'
import { getFriendlyErrorMessage } from '../api/client'
import { UserIdentity } from './UserIdentity'
import { relativeTime } from './feedHelpers'
import { ReportDialog } from './ReportDialog'
import { renderCommentContent } from './commentText'

function updateCommentCache(
  previous: InfiniteData<{ items: Comment[]; nextCursor: string | null }> | undefined,
  commentId: string,
  update: (comment: Comment) => Comment,
) {
  if (!previous) return previous
  return {
    ...previous,
    pages: previous.pages.map((page) => ({
      ...page,
      items: page.items.map((comment) => comment.id === commentId ? update(comment) : comment),
    })),
  }
}

export function CommentsSection({
  postId,
  currentUserId,
  onCommentsChanged,
}: {
  postId: string
  currentUserId: string
  onCommentsChanged: () => void
}) {
  const [content, setContent] = useState('')
  const [replyTarget, setReplyTarget] = useState<Comment | null>(null)
  const queryClient = useQueryClient()
  const queryKey = ['comments', postId]
  const commentsQuery = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => getCommentsPage(postId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
  })
  const createMutation = useMutation({
    mutationFn: ({ value, parentId }: { value: string; parentId?: string }) => createComment(postId, value, parentId),
    onMutate: async ({ value, parentId }) => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<InfiniteData<{ items: Comment[]; nextCursor: string | null }>>(queryKey)
      if (previous) {
        const optimisticComment: Comment = {
          id: `optimistic-${Date.now()}`,
          author: { id: currentUserId, username: 'you' },
          author_id: currentUserId,
          content: value,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          like_count: 0,
          liked_by_me: false,
          parent_id: parentId ?? null,
          post_id: postId,
        }
        queryClient.setQueryData(queryKey, {
          ...previous,
          pages: previous.pages.map((page, index) => index === 0 ? { ...page, items: [...page.items, optimisticComment] } : page),
        })
      }
      return { previous }
    },
    onError: (_error, _input, context) => {
      if (context?.previous) queryClient.setQueryData(queryKey, context.previous)
    },
    onSuccess: async () => {
      setContent('')
      setReplyTarget(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey }),
        Promise.resolve(onCommentsChanged()),
      ])
    },
  })
  const deleteMutation = useMutation({
    mutationFn: deleteComment,
    onSuccess: async (_result, commentId) => {
      queryClient.setQueryData(queryKey, (previous: typeof commentsQuery.data) => previous && ({
        ...previous,
        pages: previous.pages.map((page) => ({
          ...page,
          items: page.items.filter((comment) => comment.id !== commentId && comment.parent_id !== commentId),
        })),
      }))
      await Promise.all([
        queryClient.invalidateQueries({ queryKey }),
        Promise.resolve(onCommentsChanged()),
      ])
    },
  })

  const comments: Comment[] = commentsQuery.data?.pages.flatMap((page) => page.items) ?? []
  const topLevelComments = comments.filter((comment) => !comment.parent_id || !comments.some((parent) => parent.id === comment.parent_id))
  const validContent = content.trim().length > 0 && content.trim().length <= 5000

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (validContent) createMutation.mutate({ value: content.trim(), parentId: replyTarget?.id })
  }

  return (
    <section className="comments-section" aria-label="Comments">
      {commentsQuery.isPending ? (
        <div className="comment-skeleton" role="status">Loading comments…</div>
      ) : commentsQuery.isError ? (
        <div className="inline-error" role="alert">
          <p>{getFriendlyErrorMessage(commentsQuery.error)}</p>
          <button className="button button--outline" type="button" onClick={() => void commentsQuery.refetch()}>Retry</button>
        </div>
      ) : comments.length === 0 ? (
        <p className="comments-empty">No comments yet. Start a thoughtful conversation.</p>
      ) : (
        <div className="comments-list">
          {topLevelComments.map((comment) => <CommentThread
            key={comment.id}
            comment={comment}
            replies={comments.filter((reply) => reply.parent_id === comment.id)}
            postId={postId}
            currentUserId={currentUserId}
            deletePending={deleteMutation.isPending}
            onDelete={(commentId) => {
              if (window.confirm('Delete this comment?')) deleteMutation.mutate(commentId)
            }}
            onReply={(target) => {
              setReplyTarget(target)
              document.getElementById(`comment-${postId}`)?.focus()
            }}
            onCommentsChanged={onCommentsChanged}
          />)}
        </div>
      )}

      {commentsQuery.hasNextPage && (
        <button
          className="button button--outline comments-load-more"
          type="button"
          disabled={commentsQuery.isFetchingNextPage}
          onClick={() => void commentsQuery.fetchNextPage()}
        >
          {commentsQuery.isFetchingNextPage ? <LoaderCircle size={16} className="spin" /> : <MessageCircle size={16} />}
          {commentsQuery.isFetchingNextPage ? 'Loading…' : 'Load older comments'}
        </button>
      )}

      <form className="comment-composer" onSubmit={submit}>
        <label className="sr-only" htmlFor={`comment-${postId}`}>Write a comment</label>
        <textarea
          id={`comment-${postId}`}
          rows={2}
          maxLength={5000}
          value={content}
          onChange={(event) => setContent(event.currentTarget.value)}
          placeholder={replyTarget ? `Reply to @${replyTarget.author.username}…` : 'Add a comment…'}
        />
        {replyTarget && <button className="icon-button" type="button" aria-label="Cancel reply" title="Cancel reply" onClick={() => setReplyTarget(null)}><X size={16} aria-hidden="true" /></button>}
        <button className="button button--primary" type="submit" disabled={!validContent || createMutation.isPending}>
          <Send size={15} aria-hidden="true" /> {createMutation.isPending ? 'Sending…' : 'Comment'}
        </button>
      </form>
      {createMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(createMutation.error)}</p>}
      {deleteMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(deleteMutation.error)}</p>}
    </section>
  )
}

function CommentThread({
  comment,
  replies,
  postId,
  currentUserId,
  deletePending,
  onDelete,
  onReply,
  onCommentsChanged,
}: {
  comment: Comment
  replies: Comment[]
  postId: string
  currentUserId: string
  deletePending: boolean
  onDelete: (commentId: string) => void
  onReply: (comment: Comment) => void
  onCommentsChanged: () => void
}) {
  const queryClient = useQueryClient()
  const queryKey = ['comments', postId]
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(comment.content)
  const likeMutation = useMutation({
    mutationFn: (liked: boolean) => setCommentLike(comment.id, liked),
    onMutate: async (liked) => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<InfiniteData<{ items: Comment[]; nextCursor: string | null }>>(queryKey)
      queryClient.setQueryData(queryKey, (current: typeof previous) => updateCommentCache(current, comment.id, (value) => ({
        ...value,
        liked_by_me: liked,
        like_count: Math.max(0, value.like_count + (value.liked_by_me === liked ? 0 : liked ? 1 : -1)),
      })))
      return { previous }
    },
    onError: (_error, _liked, context) => {
      if (context?.previous) queryClient.setQueryData(queryKey, context.previous)
    },
    onSettled: onCommentsChanged,
  })
  const editMutation = useMutation({
    mutationFn: () => updateComment(comment.id, draft.trim()),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<InfiniteData<{ items: Comment[]; nextCursor: string | null }>>(queryKey)
      queryClient.setQueryData(queryKey, (current: typeof previous) => updateCommentCache(current, comment.id, (value) => ({ ...value, content: draft.trim() })))
      return { previous }
    },
    onError: (_error, _value, context) => {
      if (context?.previous) queryClient.setQueryData(queryKey, context.previous)
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKey, (current: InfiniteData<{ items: Comment[]; nextCursor: string | null }> | undefined) => updateCommentCache(current, comment.id, () => updated))
      setEditing(false)
      onCommentsChanged()
    },
  })

  return <div className="comment-thread">
    <article className="comment-item">
      <UserIdentity userId={comment.author_id} username={comment.author.username} currentUserId={currentUserId} compact />
      {editing ? <form className="comment-edit-form" onSubmit={(event) => { event.preventDefault(); if (draft.trim()) editMutation.mutate() }}>
        <label className="sr-only" htmlFor={`edit-comment-${comment.id}`}>Edit comment</label>
        <textarea id={`edit-comment-${comment.id}`} maxLength={5000} value={draft} onChange={(event) => setDraft(event.currentTarget.value)} />
        <button className="icon-button" type="button" aria-label="Cancel edit" title="Cancel edit" onClick={() => { setDraft(comment.content); setEditing(false) }}><X size={15} aria-hidden="true" /></button>
        <button className="icon-button" type="submit" aria-label="Save comment" title="Save comment" disabled={!draft.trim() || editMutation.isPending}><Check size={15} aria-hidden="true" /></button>
      </form> : <p className="comment-item__content">{renderCommentContent(comment.content)}</p>}
      <time dateTime={comment.created_at}>{relativeTime(comment.created_at)}</time>
      <button className={`post-action${comment.liked_by_me ? ' post-action--liked' : ''}`} type="button" aria-pressed={comment.liked_by_me} aria-label={`${comment.liked_by_me ? 'Unlike' : 'Like'} comment, ${comment.like_count} likes`} disabled={likeMutation.isPending} onClick={() => likeMutation.mutate(!comment.liked_by_me)}><Heart size={15} fill={comment.liked_by_me ? 'currentColor' : 'none'} aria-hidden="true" /><span>{comment.like_count}</span></button>
      {!comment.parent_id && <button className="button button--ghost comment-reply" type="button" onClick={() => onReply(comment)}>Reply</button>}
      {comment.author_id !== currentUserId && <ReportDialog targetType="COMMENT" targetId={comment.id} />}
      {comment.author_id === currentUserId && <>
        <button className="icon-button" type="button" aria-label="Edit comment" title="Edit comment" onClick={() => { setDraft(comment.content); setEditing(true) }}><Pencil size={15} aria-hidden="true" /></button>
        <button className="icon-button comment-item__delete" type="button" aria-label="Delete comment" title="Delete comment" disabled={deletePending} onClick={() => onDelete(comment.id)}><Trash2 size={15} aria-hidden="true" /></button>
      </>}
    </article>
    {editMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(editMutation.error)}</p>}
    {likeMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(likeMutation.error)}</p>}
    {replies.length > 0 && <div className="comment-replies" aria-label="Replies">{replies.map((reply) => <CommentThread key={reply.id} comment={reply} replies={[]} postId={postId} currentUserId={currentUserId} deletePending={deletePending} onDelete={onDelete} onReply={onReply} onCommentsChanged={onCommentsChanged} />)}</div>}
  </div>
}