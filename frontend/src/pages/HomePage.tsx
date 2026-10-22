import { lazy, Suspense, useState } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, MessageCircle } from 'lucide-react'
import { createPost, getFeed, type Post } from '../api/social'
import { getPostImageLimits } from '../api/media'
import { getFriendlyErrorMessage } from '../api/client'
import { PostComposer } from '../components/PostComposer'
import { PostCard } from '../components/PostCard'
import { PageHeader } from '../components/PageHeader'
import { GetStartedChecklist } from '../components/GetStartedChecklist'
import { useToast } from '../components/ToastProvider'
import { useAuth } from '../hooks/useAuth'

const ReelsViewer = lazy(() => import('./ReelsPage').then((module) => ({ default: module.ReelsViewer })))

const homeTabStorageKey = 'home.activeTab'
type HomeTab = 'feed' | 'reels'

export function HomePage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [activeTab, setActiveTab] = useState<HomeTab>(() => sessionStorage.getItem(homeTabStorageKey) === 'reels' ? 'reels' : 'feed')
  const feedQuery = useInfiniteQuery({
    queryKey: ['feed'],
    queryFn: ({ pageParam }) => getFeed(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.has_more ? page.next_cursor ?? undefined : undefined,
    enabled: activeTab === 'feed',
  })
  const imageLimitsQuery = useQuery({
    queryKey: ['media', 'post-image-limits'],
    queryFn: getPostImageLimits,
  })
  const createMutation = useMutation({
    mutationFn: ({ content, attachments }: { content: string; attachments: Parameters<typeof createPost>[1] }) => createPost(content, attachments),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['feed'] })
      toast('success', 'Your post was shared.')
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

  function selectTab(tab: HomeTab) {
    sessionStorage.setItem(homeTabStorageKey, tab)
    setActiveTab(tab)
  }

  return (
    <div className="page-stack" data-section="learning">
      <PageHeader section="YOUR COMMUNITY" title="Home" description={`Share what you’re learning, ${user?.username ?? 'today'}.`} />
      {user && <GetStartedChecklist userId={user.id} onWritePost={() => document.getElementById('post-content')?.focus()} />}

      <div className="home-tabs" role="tablist" aria-label="Home content">
        <button id="home-tab-feed" type="button" role="tab" aria-selected={activeTab === 'feed'} aria-controls="home-panel-feed" tabIndex={activeTab === 'feed' ? 0 : -1} className={activeTab === 'feed' ? 'is-active' : ''} onClick={() => selectTab('feed')}>Feed</button>
        <button id="home-tab-reels" type="button" role="tab" aria-selected={activeTab === 'reels'} aria-controls="home-panel-reels" tabIndex={activeTab === 'reels' ? 0 : -1} className={activeTab === 'reels' ? 'is-active' : ''} onClick={() => selectTab('reels')}>Reels</button>
      </div>

      {activeTab === 'feed' ? <section id="home-panel-feed" role="tabpanel" aria-labelledby="home-tab-feed" className="home-tab-panel">
      <PostComposer
        onPost={(content, attachments) => createMutation.mutateAsync({ content, attachments }).then(() => undefined)}
        isPosting={createMutation.isPending}
        error={createMutation.isError ? getFriendlyErrorMessage(createMutation.error) : null}
        imageLimits={imageLimitsQuery.data ?? null}
        imageLimitsError={imageLimitsQuery.isError ? getFriendlyErrorMessage(imageLimitsQuery.error) : null}
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
          <p>No posts yet. Share the first update.</p>
          <button className="button button--primary" type="button" onClick={() => document.getElementById('post-content')?.focus()}>Write a post</button>
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
      </section> : <section id="home-panel-reels" role="tabpanel" aria-labelledby="home-tab-reels" className="home-tab-panel"><Suspense fallback={<p role="status">Loading Reels…</p>}><ReelsViewer embedded /></Suspense></section>}
    </div>
  )
}