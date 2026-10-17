import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bell } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getUnreadNotificationCount } from '../api/notifications'

export function NotificationBell() {
  const [isVisible, setIsVisible] = useState(() => !document.hidden)
  useEffect(() => {
    const updateVisibility = () => setIsVisible(!document.hidden)
    document.addEventListener('visibilitychange', updateVisibility)
    return () => document.removeEventListener('visibilitychange', updateVisibility)
  }, [])

  const unreadQuery = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: getUnreadNotificationCount,
    refetchInterval: isVisible ? 30_000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  })
  const unreadCount = unreadQuery.data?.unread_count ?? 0

  return (
    <Link
      className="icon-button notification-bell__trigger"
      to="/notifications"
      aria-label={unreadQuery.isError ? 'Notifications' : `Notifications, ${unreadCount} unread`}
    >
      <Bell size={20} aria-hidden="true" />
      {unreadCount > 0 && <span className="notification-bell__badge" aria-label={`${unreadCount} unread`}>{unreadCount > 99 ? '99+' : unreadCount}</span>}
    </Link>
  )
}
