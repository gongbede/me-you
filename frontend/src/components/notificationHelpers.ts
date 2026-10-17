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
    case 'NEW_VIDEO': return actor ? `${actor} shared a video.` : 'A creator you follow shared a video.'
    case 'VIDEO_COMMENT': return actor ? `${actor} commented on your video.` : 'Someone commented on your video.'
    case 'VIDEO_LIKE': return actor ? `${actor} liked your video.` : 'Someone liked your video.'
    case 'NEW_TRACK': return actor ? `${actor} shared a music track.` : 'A new music track is available.'
    default: return notification.title
  }
}

export function notificationTargetPath(notification: Notification): string | null {
  if (
    notification.type === 'CLASS_ANNOUNCEMENT' &&
    notification.target_type === 'class_session' &&
    notification.target_id &&
    typeof notification.payload?.course_id === 'string'
  ) {
    return `/courses/${notification.payload.course_id}/classrooms/${notification.target_id}`
  }
  if (notification.type === 'MESSAGE' && notification.target_type === 'conversation' && notification.target_id) {
    return `/messages/${notification.target_id}`
  }
  if (notification.type === 'FOLLOW' && notification.target_type === 'user' && notification.target_id) {
    return `/users/${notification.target_id}`
  }
  if ((notification.type === 'LIKE' || notification.type === 'COMMENT') && notification.post_id) {
    return `/?post=${notification.post_id}#post-${notification.post_id}`
  }
  if (notification.target_type === 'VIDEO' && notification.target_id) return `/videos?id=${notification.target_id}`
  if (notification.target_type === 'TRACK' && notification.target_id) return `/music?id=${notification.target_id}`
  if (notification.target_type === 'course' && notification.target_id) {
    return `/courses/${notification.target_id}`
  }
  if (notification.target_type === 'institution' && notification.target_id) {
    return `/schools/${notification.target_id}`
  }
  return null
}