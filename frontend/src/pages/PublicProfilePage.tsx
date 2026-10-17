import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { useState } from 'react'
import { Ban, MessageCircle, UserRound, UserRoundPlus, UserRoundMinus } from 'lucide-react'
import { getFriendlyErrorMessage } from '../api/client'
import {
  followUser,
  getPublicProfile,
  getUserFollowersPage,
  getUserFollowingPage,
  getUserPosts,
  unfollowUser,
} from '../api/social'
import { useAuth } from '../hooks/useAuth'
import { createDirectConversation } from '../api/messaging'
import { blockUser, listBlockedUsers, unblockUser } from '../api/moderation'

export function PublicProfilePage() {
  const { userId = '' } = useParams()
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<'posts' | 'reels' | 'followers' | 'following'>('posts')
  const profileQuery = useQuery({
    queryKey: ['profile', 'public', userId],
    queryFn: () => getPublicProfile(userId),
    enabled: Boolean(userId),
  })
  const contentQuery = useInfiniteQuery({
    queryKey: ['profile', 'content', userId, activeTab],
    queryFn: ({ pageParam }) => getUserPosts(userId, activeTab === 'reels' ? 'REEL' : 'POST', pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: Boolean(profileQuery.data && (activeTab === 'posts' || activeTab === 'reels')),
  })
  const peopleQuery = useInfiniteQuery({
    queryKey: ['profile', 'people', userId, activeTab],
    queryFn: ({ pageParam }) => activeTab === 'followers'
      ? getUserFollowersPage(userId, pageParam)
      : getUserFollowingPage(userId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: Boolean(profileQuery.data && (activeTab === 'followers' || activeTab === 'following')),
  })
  const followMutation = useMutation({
    mutationFn: async (isFollowing: boolean) => {
      if (isFollowing) await unfollowUser(userId)
      else await followUser(userId)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['profile', 'public', userId] })
    },
  })
  const messageMutation = useMutation({
    mutationFn: () => createDirectConversation(userId),
    onSuccess: async (conversation) => {
      await queryClient.invalidateQueries({ queryKey: ['messages', 'conversations'] })
      navigate(`/messages/${conversation.id}`)
    },
  })
  const blocksQuery = useQuery({
    queryKey: ['moderation', 'blocks'],
    queryFn: () => listBlockedUsers(),
    enabled: Boolean(currentUser && userId !== currentUser.id),
  })
  const blockMutation = useMutation({
    mutationFn: (blocked: boolean) => blocked ? unblockUser(userId) : blockUser(userId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['moderation', 'blocks'] }),
        queryClient.invalidateQueries({ queryKey: ['feed'] }),
        queryClient.invalidateQueries({ queryKey: ['reels'] }),
      ])
    },
  })

  if (profileQuery.isPending) return <div className="page-state" role="status">Loading profile…</div>
  if (profileQuery.isError) return (
    <div className="page-state page-state--error" role="alert">
      <h1>We couldn’t find this profile.</h1>
      <p>{getFriendlyErrorMessage(profileQuery.error)}</p>
      <button className="button button--outline" type="button" onClick={() => void profileQuery.refetch()}>Retry</button>
    </div>
  )

  const profile = profileQuery.data
  const isSelf = currentUser?.id === userId
  const isFollowing = profile.is_following
  const isBlocked = Boolean(blocksQuery.data?.some((blocked) => blocked.id === userId))
  const profilePosts = contentQuery.data?.pages.flatMap((page) => page.items) ?? []
  const listedPeople = peopleQuery.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <div className="page-stack profile-page">
      <section className="page-heading-row">
        <div><span className="eyebrow">COMMUNITY</span><h1>{profile.display_name}</h1></div>
        {!isSelf && currentUser && !isBlocked && <button className="button button--outline" type="button" disabled={messageMutation.isPending} onClick={() => messageMutation.mutate()}><MessageCircle size={17} aria-hidden="true" />{messageMutation.isPending ? 'Opening…' : 'Message'}</button>}
        {!isSelf && currentUser && <button className="button button--outline" type="button" disabled={blocksQuery.isPending || blockMutation.isPending} onClick={() => {
          if (window.confirm(`${isBlocked ? 'Unblock' : 'Block'} ${profile.display_name}?`)) blockMutation.mutate(isBlocked)
        }}><Ban size={17} aria-hidden="true" />{blockMutation.isPending ? 'Saving…' : isBlocked ? 'Unblock' : 'Block user'}</button>}
        {!isSelf && currentUser && !isBlocked && (
          <button
            className={`button ${isFollowing ? 'button--outline' : 'button--primary'}`}
            type="button"
            disabled={followMutation.isPending}
            onClick={() => followMutation.mutate(isFollowing)}
          >
            {isFollowing ? <UserRoundMinus size={17} aria-hidden="true" /> : <UserRoundPlus size={17} aria-hidden="true" />}
            {followMutation.isPending ? 'Saving…' : isFollowing ? 'Unfollow' : 'Follow'}
          </button>
        )}
      </section>
      {followMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(followMutation.error)}</p>}
      {messageMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(messageMutation.error)}</p>}
      {blocksQuery.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(blocksQuery.error)}</p>}
      {blockMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(blockMutation.error)}</p>}
      <section className="profile-card" aria-label={`${profile.display_name}'s profile`}>
        <div className="profile-card__identity">
          <div className="profile-avatar">
            {profile.profile_picture_url ? <img src={profile.profile_picture_url} alt={`${profile.display_name}'s avatar`} /> : <UserRound size={30} aria-hidden="true" />}
          </div>
          <div className="profile-card__intro">
            <span className="eyebrow">PROFILE</span>
            <h2>{profile.display_name}</h2>
            <p>@{profile.username} · Joined {new Date(profile.joined_at).toLocaleDateString()}</p>
          </div>
        </div>
        <div className="profile-details">
          <div><span>ABOUT</span><p>{profile.bio || 'Nothing here yet.'}</p></div>
          <div className="profile-form__grid">
            <div><span>LOCATION</span><p>{profile.location || 'Not added'}</p></div>
            <div><span>WEBSITE</span><p>{profile.website ? <a href={profile.website} target="_blank" rel="noreferrer">{profile.website}</a> : 'Not added'}</p></div>
          </div>
        </div>
      </section>
      <section className="card profile-activity" aria-label="Profile activity">
        <div className="profile-stats">
          <span><strong>{profile.post_count}</strong> posts</span>
          <span><strong>{profile.reel_count}</strong> reels</span>
          <button type="button" onClick={() => setActiveTab('followers')}><strong>{profile.follower_count}</strong> followers</button>
          <button type="button" onClick={() => setActiveTab('following')}><strong>{profile.following_count}</strong> following</button>
        </div>
        <div className="profile-tabs" role="tablist" aria-label="Profile content">
          {(['posts', 'reels', 'followers', 'following'] as const).map((tab) => (
            <button key={tab} role="tab" type="button" aria-selected={activeTab === tab} onClick={() => setActiveTab(tab)}>
              {tab[0].toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        {(activeTab === 'posts' || activeTab === 'reels') && (
          contentQuery.isPending ? <p className="learning-loading" role="status">Loading {activeTab}…</p> : contentQuery.isError ? (
            <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(contentQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void contentQuery.refetch()}>Retry</button></div>
          ) : profilePosts.length === 0 ? <p className="muted-copy">No {activeTab} to show.</p> : (
            <>
              <ul className="profile-post-list">
                {profilePosts.map((post) => <li key={post.id}>
                  <Link to={`/posts/${post.id}`}><span>{post.content}</span><time dateTime={post.created_at}>{new Date(post.created_at).toLocaleDateString()}</time></Link>
                </li>)}
              </ul>
              {contentQuery.hasNextPage && <button className="button button--outline" type="button" disabled={contentQuery.isFetchingNextPage} onClick={() => void contentQuery.fetchNextPage()}>{contentQuery.isFetchingNextPage ? 'Loading…' : `Load more ${activeTab}`}</button>}
            </>
          )
        )}
        {(activeTab === 'followers' || activeTab === 'following') && (
          peopleQuery.isPending ? <p className="learning-loading" role="status">Loading {activeTab}…</p> : peopleQuery.isError ? (
            <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(peopleQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void peopleQuery.refetch()}>Retry</button></div>
          ) : listedPeople.length === 0 ? <p className="muted-copy">No {activeTab} yet.</p> : (
            <>
              <ul className="profile-people-list">
                {listedPeople.map((person) => <li key={person.id}><Link to={`/users/${person.id}`}>@{person.username}</Link></li>)}
              </ul>
              {peopleQuery.hasNextPage && <button className="button button--outline" type="button" disabled={peopleQuery.isFetchingNextPage} onClick={() => void peopleQuery.fetchNextPage()}>{peopleQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}</button>}
            </>
          )
        )}
      </section>
    </div>
  )
}