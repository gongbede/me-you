import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCheck, LoaderCircle, RotateCw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import { getNotificationsPage, markAllNotificationsRead, markNotificationRead } from '../api/notifications'
import { NotificationItem } from '../components/NotificationItem'
import { notificationTargetPath } from '../components/notificationHelpers'

const unreadKey = ['notifications', 'unread-count'] as const

export function NotificationsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const pageKey = ['notifications', 'pages'] as const
  const notificationsQuery = useInfiniteQuery({
    queryKey: pageKey,
    queryFn: ({ pageParam }) => getNotificationsPage(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
  })
  const refresh = async () => Promise.all([
    queryClient.invalidateQueries({ queryKey: unreadKey }),
    queryClient.invalidateQueries({ queryKey: pageKey }),
    queryClient.invalidateQueries({ queryKey: ['notifications', 'preview'] }),
  ])
  const markOneMutation = useMutation({ mutationFn: markNotificationRead, onSuccess: refresh })
  const markAllMutation = useMutation({ mutationFn: markAllNotificationsRead, onSuccess: refresh })
  const notifications = notificationsQuery.data?.pages.flatMap((page) => page.items) ?? []

  async function activateNotification(notification: (typeof notifications)[number]) {
    try {
      if (!notification.read_at) await markOneMutation.mutateAsync(notification.id)
      const target = notificationTargetPath(notification)
      if (target) navigate(target)
    } catch {
      return
    }
  }

  return (
    <div className="page-stack notifications-page">
      <section className="page-heading-row learning-heading">
        <div><span className="eyebrow">YOUR COMMUNITY</span><h1>Notifications</h1><p>Updates about your community and learning.</p></div>
        <button className="button button--outline" type="button" disabled={markAllMutation.isPending || !notifications.some((notification) => !notification.read_at)} onClick={() => markAllMutation.mutate()}><CheckCheck size={16} aria-hidden="true" /> Mark all as read</button>
      </section>
      {notificationsQuery.isPending ? <p className="learning-loading" role="status">Loading notifications…</p> : notificationsQuery.isError && !notificationsQuery.data ? (
        <div className="page-state page-state--error" role="alert"><h2>Notifications unavailable</h2><p>{getFriendlyErrorMessage(notificationsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void notificationsQuery.refetch()}><RotateCw size={16} aria-hidden="true" /> Retry</button></div>
      ) : notifications.length === 0 ? <p className="notification-empty notification-empty--page">You’re all caught up.</p> : (
        <ul className="notification-list notification-list--page">
          {notifications.map((notification) => <NotificationItem
            key={notification.id}
            notification={notification}
            onActivate={(value) => void activateNotification(value)}
            onMarkRead={(id) => markOneMutation.mutate(id)}
          />)}
        </ul>
      )}
      {(markOneMutation.isError || markAllMutation.isError || notificationsQuery.isFetchNextPageError) && <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(markOneMutation.error ?? markAllMutation.error ?? notificationsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => notificationsQuery.isFetchNextPageError ? void notificationsQuery.fetchNextPage() : void refresh()}>Retry</button></div>}
      {notificationsQuery.hasNextPage && <button className="button button--outline feed-load-more" type="button" disabled={notificationsQuery.isFetchingNextPage} onClick={() => void notificationsQuery.fetchNextPage()}>{notificationsQuery.isFetchingNextPage && <LoaderCircle className="spin" size={16} aria-hidden="true" />}{notificationsQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}</button>}
    </div>
  )
}