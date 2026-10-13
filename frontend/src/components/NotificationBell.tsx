import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCheck, RotateCw } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import { getNotificationsPage, getUnreadNotificationCount, markAllNotificationsRead, markNotificationRead, type Notification } from '../api/notifications'
import { NotificationItem } from './NotificationItem'
import { notificationTargetPath } from './notificationHelpers'

const unreadKey = ['notifications', 'unread-count'] as const
const previewKey = ['notifications', 'preview'] as const

export function NotificationBell() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [isVisible, setIsVisible] = useState(() => !document.hidden)
  useEffect(() => {
    const updateVisibility = () => setIsVisible(!document.hidden)
    document.addEventListener('visibilitychange', updateVisibility)
    return () => document.removeEventListener('visibilitychange', updateVisibility)
  }, [])
  useEffect(() => {
    if (!isOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false)
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [isOpen])

  const unreadQuery = useQuery({
    queryKey: unreadKey,
    queryFn: getUnreadNotificationCount,
    refetchInterval: isVisible ? 30_000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  })
  const previewQuery = useQuery({
    queryKey: previewKey,
    queryFn: () => getNotificationsPage(undefined, 8),
    enabled: isOpen,
  })
  const markOneMutation = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: unreadKey }),
        queryClient.invalidateQueries({ queryKey: previewKey }),
        queryClient.invalidateQueries({ queryKey: ['notifications', 'pages'] }),
      ])
    },
  })
  const markAllMutation = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: unreadKey }),
        queryClient.invalidateQueries({ queryKey: previewKey }),
        queryClient.invalidateQueries({ queryKey: ['notifications', 'pages'] }),
      ])
    },
  })
  const unreadCount = unreadQuery.data?.unread_count ?? 0

  async function activateNotification(notification: Notification) {
    try {
      if (!notification.read_at) await markOneMutation.mutateAsync(notification.id)
      const target = notificationTargetPath(notification)
      setIsOpen(false)
      if (target) navigate(target)
    } catch {
      return
    }
  }

  return (
    <div className="notification-bell">
      <button
        className="icon-button notification-bell__trigger"
        type="button"
        aria-label={unreadQuery.isError ? 'Notifications' : `Notifications, ${unreadCount} unread`}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        onClick={() => setIsOpen((open) => !open)}
      >
        <Bell size={20} aria-hidden="true" />
        {unreadCount > 0 && <span className="notification-bell__badge" aria-label={`${unreadCount} unread`}>{unreadCount > 99 ? '99+' : unreadCount}</span>}
      </button>
      {isOpen && <section className="notification-panel" role="dialog" aria-label="Latest notifications">
        <header className="notification-panel__header">
          <h2>Notifications</h2>
          <button className="button button--outline" type="button" disabled={!unreadCount || markAllMutation.isPending} onClick={() => markAllMutation.mutate()}><CheckCheck size={15} aria-hidden="true" /> Mark all as read</button>
        </header>
        {previewQuery.isPending ? <p className="learning-loading" role="status">Loading notifications…</p> : previewQuery.isError ? (
          <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(previewQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void previewQuery.refetch()}><RotateCw size={15} aria-hidden="true" /> Retry</button></div>
        ) : previewQuery.data.items.length === 0 ? <p className="notification-empty">You’re all caught up.</p> : (
          <ul className="notification-list">
            {previewQuery.data.items.map((notification) => <NotificationItem
              key={notification.id}
              notification={notification}
              onActivate={(value) => void activateNotification(value)}
              onMarkRead={(id) => markOneMutation.mutate(id)}
            />)}
          </ul>
        )}
        {(markOneMutation.isError || markAllMutation.isError) && <p className="form-alert" role="alert">{getFriendlyErrorMessage(markOneMutation.error ?? markAllMutation.error)}</p>}
        <Link className="notification-panel__all" to="/notifications" onClick={() => setIsOpen(false)}>See all notifications</Link>
      </section>}
    </div>
  )
}