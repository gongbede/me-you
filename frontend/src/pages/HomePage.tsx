import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, MessageCircle } from 'lucide-react'
import { createPost, getFeed, type Post } from '../api/social'
import { getFriendlyErrorMessage } from '../api/client'
import { PostComposer } from '../components/PostComposer'
import { PostCard } from '../components/PostCard'
import { useAuth } from '../hooks/useAuth'

export function HomePage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const feedQuery = useInfiniteQuery({
    queryKey: ['feed'],
    queryFn: ({ pageParam }) => getFeed(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.has_more ? page.next_cursor ?? undefined : undefined,
  })
  const createMutation = useMutation({
    mutationFn: createPost,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['feed'] })
    },
  })
  const posts: Post[] = feedQuery.data?.pages.flatMap((page) => page.items) ?? []

  function removePost(postId: string) {
    queryClient.setQueryData(['feed'], (previous: typeof feedQuery.data) => previous && ({
      ...previous,
      pages: previous.pages.map((page) => ({
        ...page,
        items: page.items.filter((post) => post.id !== postId),
      })),
    }))
    void queryClient.invalidateQueries({ queryKey: ['feed'] })
  }

  return (
    <div className="page-stack">
      <section className="page-heading-row feed-heading">
        <div>
          <span className="eyebrow">YOUR COMMUNITY</span>
          <h1>Home</h1>
          <p>Share what you’re learning, {user?.username}.</p>
        </div>
      </section>

      <PostComposer
        onPost={(content) => createMutation.mutateAsync(content).then(() => undefined)}
        isPosting={createMutation.isPending}
        error={createMutation.isError ? getFriendlyErrorMessage(createMutation.error) : null}
      />

      {feedQuery.isPending ? (
        <div className="feed-list" role="status" aria-label="Loading posts">
          {[0, 1, 2].map((key) => <div className="post-skeleton" key={key}><span /><span /><span /></div>)}
        </div>
      ) : feedQuery.isError && !feedQuery.data ? (
        <div className="page-state page-state--error" role="alert">
          <h2>We couldn’t load your feed.</h2>
          <p>{getFriendlyErrorMessage(feedQuery.error)}</p>
          <button className="button button--outline" type="button" onClick={() => void feedQuery.refetch()}>Retry</button>
        </div>
      ) : posts.length === 0 ? (
        <div className="feed-empty">
          <MessageCircle size={24} aria-hidden="true" />
          <p>Nothing here yet. Be the first to post.</p>
        </div>
      ) : (
        <div className="feed-list" aria-label="Your feed">
          {posts.map((post) => <PostCard key={post.id} post={post} onDeleted={removePost} />)}
        </div>
      )}

      {feedQuery.hasNextPage && (
        <button
          className="button button--outline feed-load-more"
          type="button"
          disabled={feedQuery.isFetchingNextPage}
          onClick={() => void feedQuery.fetchNextPage()}
        >
          {feedQuery.isFetchingNextPage && <LoaderCircle size={16} className="spin" aria-hidden="true" />}
          {feedQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}
        </button>
      )}
      {feedQuery.isFetchNextPageError && (
        <div className="inline-error" role="alert">
          <p>{getFriendlyErrorMessage(feedQuery.error)}</p>
          <button className="button button--outline" type="button" onClick={() => void feedQuery.fetchNextPage()}>Retry</button>
        </div>
      )}
    </div>
  )
}