import { ArrowUpRight, Bell, BookOpen, Check, Heart, MessageCircle, Music2, UserRoundPlus, Video } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Notification } from '../api/notifications'
import { notificationTargetPath, notificationText } from './notificationHelpers'

export function NotificationItem({
  notification,
  now,
  onActivate,
  onMarkRead,
}: {
  notification: Notification
  now: number
  onActivate: (notification: Notification) => void
  onMarkRead: (notificationId: string) => void
}) {
  const target = notificationTargetPath(notification)
  const text = notificationText(notification)
  const Icon = notification.type === 'FOLLOW'
    ? UserRoundPlus
    : ['LIKE', 'COMMENT_LIKE', 'VIDEO_LIKE'].includes(notification.type)
      ? Heart
      : notification.type === 'MESSAGE'
        ? MessageCircle
        : ['NEW_VIDEO', 'VIDEO_COMMENT'].includes(notification.type)
          ? Video
          : notification.type === 'NEW_TRACK'
            ? Music2
            : ['CLASS_ANNOUNCEMENT', 'EXERCISE_SUBMISSION', 'EXERCISE_REVIEWED'].includes(notification.type)
              ? BookOpen
              : Bell
  const createdAt = new Date(notification.created_at)
  const secondsAgo = Math.max(0, Math.floor((now - createdAt.getTime()) / 1000))
  const relativeTime = secondsAgo < 60
    ? 'just now'
    : new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
      -Math.floor(secondsAgo / (secondsAgo < 3600 ? 60 : secondsAgo < 86_400 ? 3600 : 86_400)),
      secondsAgo < 3600 ? 'minute' : secondsAgo < 86_400 ? 'hour' : 'day',
    )
  return (
    <li className={`notification-item${notification.read_at ? '' : ' notification-item--unread'}`}>
      <span className={`notification-item__icon notification-item__icon--${notification.type.toLowerCase()}`} aria-hidden="true"><Icon size={18} /></span>
      <div className="notification-item__copy">
        {target ? (
          <Link to={target} className="notification-item__target" onClick={(event) => { event.preventDefault(); onActivate(notification) }}>
            <strong>{text}</strong><ArrowUpRight size={15} aria-hidden="true" />
          </Link>
        ) : (
          <button className="notification-item__target" type="button" onClick={() => onActivate(notification)}>
            <strong>{text}</strong>
          </button>
        )}
        <time dateTime={notification.created_at} title={createdAt.toLocaleString()}>{relativeTime}</time>
      </div>
      {!notification.read_at && <button className="icon-button notification-item__read" type="button" aria-label="Mark as read" title="Mark as read" onClick={() => onMarkRead(notification.id)}><Check size={16} aria-hidden="true" /></button>}
    </li>
  )
}