import { ArrowUpRight, Check } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Notification } from '../api/notifications'
import { notificationTargetPath, notificationText } from './notificationHelpers'

export function NotificationItem({
  notification,
  onActivate,
  onMarkRead,
}: {
  notification: Notification
  onActivate: (notification: Notification) => void
  onMarkRead: (notificationId: string) => void
}) {
  const target = notificationTargetPath(notification)
  const text = notificationText(notification)
  return (
    <li className={`notification-item${notification.read_at ? '' : ' notification-item--unread'}`}>
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
        <time dateTime={notification.created_at}>{new Date(notification.created_at).toLocaleString()}</time>
      </div>
      {!notification.read_at && <button className="icon-button notification-item__read" type="button" aria-label="Mark as read" title="Mark as read" onClick={() => onMarkRead(notification.id)}><Check size={16} aria-hidden="true" /></button>}
    </li>
  )
}