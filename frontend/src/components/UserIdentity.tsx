import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getPublicProfile } from '../api/social'

export function UserIdentity({
  userId,
  username,
  displayName,
  avatarUrl,
  currentUserId,
  compact = false,
}: {
  userId: string
  username: string
  displayName?: string
  avatarUrl?: string | null
  currentUserId: string
  compact?: boolean
}) {
  const profileQuery = useQuery({
    queryKey: ['profile', 'public', userId],
    queryFn: () => getPublicProfile(userId),
    retry: false,
    enabled: displayName === undefined,
  })
  const profile = profileQuery.data
  const name = displayName ?? profile?.display_name ?? username
  const avatar = displayName === undefined ? profile?.profile_picture_url : avatarUrl
  const href = userId === currentUserId ? '/profile' : `/users/${userId}`

  return (
    <div className={`user-identity${compact ? ' user-identity--compact' : ''}`}>
      <Link className="user-identity__avatar" to={href} aria-label={`View ${name}'s profile`}>
        {avatar
          ? <img src={avatar} alt={`${name}'s avatar`} />
          : <span aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>}
      </Link>
      <Link className="user-identity__name" to={href}>{name}</Link>
      {profile?.display_name && <span className="user-identity__username">@{username}</span>}
    </div>
  )
}