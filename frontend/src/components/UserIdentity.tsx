import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getPublicProfile } from '../api/social'

export function UserIdentity({
  userId,
  username,
  currentUserId,
  compact = false,
}: {
  userId: string
  username: string
  currentUserId: string
  compact?: boolean
}) {
  const profileQuery = useQuery({
    queryKey: ['profile', 'public', userId],
    queryFn: () => getPublicProfile(userId),
    retry: false,
  })
  const profile = profileQuery.data
  const name = profile?.display_name || username
  const href = userId === currentUserId ? '/profile' : `/users/${userId}`

  return (
    <div className={`user-identity${compact ? ' user-identity--compact' : ''}`}>
      <Link className="user-identity__avatar" to={href} aria-label={`View ${name}'s profile`}>
        {profile?.profile_picture_url
          ? <img src={profile.profile_picture_url} alt={`${name}'s avatar`} />
          : <span aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>}
      </Link>
      <Link className="user-identity__name" to={href}>{name}</Link>
      {profile?.display_name && <span className="user-identity__username">@{username}</span>}
    </div>
  )
}