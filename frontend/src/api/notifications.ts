import { apiRequest, apiRequestWithCursor, type ApiSchemas } from './client'

export type Notification = ApiSchemas['NotificationResponse']

export async function getNotificationsPage(cursor?: string, limit = 20): Promise<{
  items: Notification[]
  nextCursor: string | null
}> {
  const query = new URLSearchParams({ limit: String(limit) })
  if (cursor) query.set('cursor', cursor)
  const page = await apiRequestWithCursor<Notification[]>(`/api/v1/notifications?${query}`)
  return { items: page.data, nextCursor: page.nextCursor }
}

export function getUnreadNotificationCount(): Promise<ApiSchemas['NotificationUnreadCountResponse']> {
  return apiRequest('/api/v1/notifications/unread-count')
}

export function markNotificationRead(notificationId: string): Promise<Notification> {
  return apiRequest(`/api/v1/notifications/${notificationId}/read`, { method: 'POST' })
}

export function markAllNotificationsRead(): Promise<{ updated: number }> {
  return apiRequest('/api/v1/notifications/read-all', { method: 'POST' })
}