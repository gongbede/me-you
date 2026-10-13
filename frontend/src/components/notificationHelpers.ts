import type { Notification } from '../api/notifications'

export function notificationText(notification: Notification): string {
  const actor = notification.actor?.username
  switch (notification.type) {
    case 'LIKE': return actor ? `${actor} liked your post.` : 'Someone liked your post.'
    case 'COMMENT': return actor ? `${actor} commented on your post.` : 'Someone commented on your post.'
    case 'FOLLOW': return actor ? `${actor} started following you.` : 'You have a new follower.'
    case 'MESSAGE': return actor ? `${actor} sent you a message.` : 'You have a new message.'
    case 'CLASS_ANNOUNCEMENT': return 'A teacher posted a class announcement.'
    case 'EXERCISE_SUBMISSION': return actor ? `${actor} submitted an exercise.` : 'A learner submitted an exercise.'
    case 'EXERCISE_REVIEWED': return 'Your exercise submission was reviewed.'
    default: return notification.title
  }
}

export function notificationTargetPath(notification: Notification): string | null {
  if (notification.type === 'MESSAGE' && notification.target_type === 'conversation' && notification.target_id) {
    return `/messages/${notification.target_id}`
  }
  if (notification.type === 'FOLLOW' && notification.target_type === 'user' && notification.target_id) {
    return `/users/${notification.target_id}`
  }
  if ((notification.type === 'LIKE' || notification.type === 'COMMENT') && notification.post_id) {
    return `/?post=${notification.post_id}#post-${notification.post_id}`
  }
  if (notification.target_type === 'course' && notification.target_id) {
    return `/courses/${notification.target_id}`
  }
  if (notification.target_type === 'institution' && notification.target_id) {
    return `/schools/${notification.target_id}`
  }
  return null
}