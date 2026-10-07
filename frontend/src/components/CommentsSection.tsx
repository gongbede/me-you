import { useState, type FormEvent } from 'react'
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, MessageCircle, Send, Trash2 } from 'lucide-react'
import { createComment, deleteComment, getCommentsPage, type Comment } from '../api/social'
import { getFriendlyErrorMessage } from '../api/client'
import { UserIdentity } from './UserIdentity'
import { relativeTime } from './feedHelpers'

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
  const queryClient = useQueryClient()
  const queryKey = ['comments', postId]
  const commentsQuery = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => getCommentsPage(postId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
  })
  const createMutation = useMutation({
    mutationFn: (value: string) => createComment(postId, value),
    onSuccess: async () => {
      setContent('')
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
          items: page.items.filter((comment) => comment.id !== commentId),
        })),
      }))
      await Promise.resolve(onCommentsChanged())
    },
  })

  const comments: Comment[] = commentsQuery.data?.pages.flatMap((page) => page.items) ?? []
  const validContent = content.trim().length > 0 && content.trim().length <= 5000

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (validContent) createMutation.mutate(content.trim())
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
          {comments.map((comment) => (
            <article className="comment-item" key={comment.id}>
              <UserIdentity
                userId={comment.author_id}
                username={comment.author.username}
                currentUserId={currentUserId}
                compact
              />
              <p className="comment-item__content">{comment.content}</p>
              <time dateTime={comment.created_at}>{relativeTime(comment.created_at)}</time>
              {comment.author_id === currentUserId && (
                <button
                  className="icon-button comment-item__delete"
                  type="button"
                  aria-label="Delete comment"
                  title="Delete comment"
                  disabled={deleteMutation.isPending}
                  onClick={() => {
                    if (window.confirm('Delete this comment?')) deleteMutation.mutate(comment.id)
                  }}
                >
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              )}
            </article>
          ))}
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
          placeholder="Add a comment…"
        />
        <button className="button button--primary" type="submit" disabled={!validContent || createMutation.isPending}>
          <Send size={15} aria-hidden="true" /> {createMutation.isPending ? 'Sending…' : 'Comment'}
        </button>
      </form>
      {createMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(createMutation.error)}</p>}
      {deleteMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(deleteMutation.error)}</p>}
    </section>
  )
}