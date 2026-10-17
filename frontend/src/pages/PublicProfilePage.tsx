import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { Ban, MessageCircle, UserRound, UserRoundPlus, UserRoundMinus } from 'lucide-react'
import { getFriendlyErrorMessage } from '../api/client'
import { followUser, getPublicProfile, getUserFollowers, unfollowUser } from '../api/social'
import { useAuth } from '../hooks/useAuth'
import { createDirectConversation } from '../api/messaging'
import { blockUser, listBlockedUsers, unblockUser } from '../api/moderation'

export function PublicProfilePage() {
  const { userId = '' } = useParams()
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const profileQuery = useQuery({
    queryKey: ['profile', 'public', userId],
    queryFn: () => getPublicProfile(userId),
    enabled: Boolean(userId),
  })
  const followersQuery = useQuery({
    queryKey: ['profile', 'followers', userId],
    queryFn: () => getUserFollowers(userId),
    enabled: Boolean(userId && currentUser && userId !== currentUser.id && profileQuery.data),
  })
  const followMutation = useMutation({
    mutationFn: async (isFollowing: boolean) => {
      if (isFollowing) await unfollowUser(userId)
      else await followUser(userId)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['profile', 'followers', userId] })
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
  const isFollowing = Boolean(followersQuery.data?.some((follower) => follower.id === currentUser?.id))
  const isBlocked = Boolean(blocksQuery.data?.some((blocked) => blocked.id === userId))

  return (
    <div className="page-stack profile-page">
      <section className="page-heading-row">
        <div><span className="eyebrow">COMMUNITY</span><h1>{profile.display_name}</h1></div>
        {!isSelf && currentUser && <button className="button button--outline" type="button" disabled={messageMutation.isPending} onClick={() => messageMutation.mutate()}><MessageCircle size={17} aria-hidden="true" />{messageMutation.isPending ? 'Opening…' : 'Message'}</button>}
        {!isSelf && currentUser && <button className="button button--outline" type="button" disabled={blocksQuery.isPending || blockMutation.isPending} onClick={() => {
          if (window.confirm(`${isBlocked ? 'Unblock' : 'Block'} ${profile.display_name}?`)) blockMutation.mutate(isBlocked)
        }}><Ban size={17} aria-hidden="true" />{blockMutation.isPending ? 'Saving…' : isBlocked ? 'Unblock' : 'Block user'}</button>}
        {!isSelf && currentUser && !followersQuery.isPending && !followersQuery.isError && (
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
      {followersQuery.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(followersQuery.error)}</p>}
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
            <p>Visible to {profile.visibility.toLowerCase()} viewers</p>
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
    </div>
  )
}