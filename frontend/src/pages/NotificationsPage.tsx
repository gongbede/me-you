import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCheck, LoaderCircle, RotateCw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getFriendlyErrorMessage } from '../api/client'
import { getNotificationsPage, getUnreadNotificationCount, markAllNotificationsRead, markNotificationRead } from '../api/notifications'
import { NotificationItem } from '../components/NotificationItem'
import { notificationTargetPath } from '../components/notificationHelpers'
import { PageHeader } from '../components/PageHeader'

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
  const unreadQuery = useQuery({
    queryKey: unreadKey,
    queryFn: getUnreadNotificationCount,
    refetchOnWindowFocus: true,
  })
  const refresh = async () => Promise.all([
    queryClient.invalidateQueries({ queryKey: unreadKey }),
    queryClient.invalidateQueries({ queryKey: pageKey }),
    queryClient.invalidateQueries({ queryKey: ['notifications', 'preview'] }),
  ])
  const markOneMutation = useMutation({ mutationFn: markNotificationRead, onSuccess: refresh })
  const markAllMutation = useMutation({ mutationFn: markAllNotificationsRead, onSuccess: refresh })
  const notifications = notificationsQuery.data?.pages.flatMap((page) => page.items) ?? []
  const [mediaFilter, setMediaFilter] = useState(false)
  const [now, setNow] = useState(0)
  useEffect(() => {
    const updateTime = () => setNow(Date.now())
    updateTime()
    const interval = window.setInterval(updateTime, 60_000)
    return () => window.clearInterval(interval)
  }, [])
  const visibleNotifications = mediaFilter
    ? notifications.filter((notification) => notification.type === 'NEW_TRACK')
    : notifications
  const groupedNotifications = [
    { title: 'Community', types: ['COMMENT', 'FOLLOW', 'LIKE', 'MENTION', 'COMMENT_LIKE'] },
    { title: 'Messages', types: ['MESSAGE'] },
    { title: 'Learning', types: ['CLASS_ANNOUNCEMENT', 'EXERCISE_SUBMISSION', 'EXERCISE_REVIEWED'] },
    { title: 'Media', types: ['NEW_VIDEO', 'VIDEO_COMMENT', 'VIDEO_LIKE', 'NEW_TRACK'] },
  ].map((group) => ({
    ...group,
    items: visibleNotifications.filter((notification) => group.types.includes(notification.type)),
  })).filter((group) => group.items.length > 0)

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
      <PageHeader section="YOUR COMMUNITY" title="Notifications" description="Updates about your community and learning." action={<button className="button button--outline" type="button" disabled={markAllMutation.isPending || unreadQuery.isPending || unreadQuery.data?.unread_count === 0} onClick={() => markAllMutation.mutate()}><CheckCheck size={16} aria-hidden="true" /> Mark all as read</button>} />
      <div className="chip-row notifications-filters" role="group" aria-label="Notification filters">
        <button className={`chip${!mediaFilter ? ' is-active' : ''}`} type="button" aria-pressed={!mediaFilter} onClick={() => setMediaFilter(false)}>All updates</button>
        <button className={`chip${mediaFilter ? ' is-active' : ''}`} type="button" aria-pressed={mediaFilter} onClick={() => setMediaFilter(true)}>Music</button>
      </div>
      {notificationsQuery.isPending ? <div className="notification-skeleton-list" role="status" aria-label="Loading notifications">{[0, 1, 2].map((key) => <div className="notification-skeleton" key={key}><span /><span /><span /></div>)}</div> : notificationsQuery.isError && !notificationsQuery.data ? (
        <div className="page-state page-state--error" role="alert"><h2>Notifications unavailable</h2><p>{getFriendlyErrorMessage(notificationsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void notificationsQuery.refetch()}><RotateCw size={16} aria-hidden="true" /> Retry</button></div>
      ) : visibleNotifications.length === 0 ? <p className="notification-empty notification-empty--page">You’re all caught up.</p> : (
        <div className="notification-groups">
          {groupedNotifications.map((group) => <section className="notification-group" key={group.title} aria-label={`${group.title} notifications`}>
            <h2>{group.title}</h2>
            <ul className="notification-list notification-list--page">
              {group.items.map((notification) => <NotificationItem
                key={notification.id}
                notification={notification}
                now={now}
                onActivate={(value) => void activateNotification(value)}
                onMarkRead={(id) => markOneMutation.mutate(id)}
              />)}
            </ul>
          </section>)}
        </div>
      )}
      {(markOneMutation.isError || markAllMutation.isError || notificationsQuery.isFetchNextPageError) && <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(markOneMutation.error ?? markAllMutation.error ?? notificationsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => notificationsQuery.isFetchNextPageError ? void notificationsQuery.fetchNextPage() : void refresh()}>Retry</button></div>}
      {unreadQuery.isError && <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(unreadQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void unreadQuery.refetch()}>Retry unread count</button></div>}
      {notificationsQuery.hasNextPage && <button className="button button--outline feed-load-more" type="button" disabled={notificationsQuery.isFetchingNextPage} onClick={() => void notificationsQuery.fetchNextPage()}>{notificationsQuery.isFetchingNextPage && <LoaderCircle className="spin" size={16} aria-hidden="true" />}{notificationsQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}</button>}
    </div>
  )
}