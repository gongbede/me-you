import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { UserRound, UserRoundPlus, UserRoundMinus } from 'lucide-react'
import { getFriendlyErrorMessage } from '../api/client'
import { followUser, getPublicProfile, getUserFollowers, unfollowUser } from '../api/social'
import { useAuth } from '../hooks/useAuth'

export function PublicProfilePage() {
  const { userId = '' } = useParams()
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
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

  return (
    <div className="page-stack profile-page">
      <section className="page-heading-row">
        <div><span className="eyebrow">COMMUNITY</span><h1>{profile.display_name}</h1></div>
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