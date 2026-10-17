import { apiRequest, type ApiSchemas } from './client'

export type ReportTargetType = ApiSchemas['ReportCreate']['target_type']
export type ReportReason = ApiSchemas['ReportCreate']['reason']
export type Report = ApiSchemas['ReportResponse']
export type BlockedUser = ApiSchemas['BlockedUserResponse']

export function submitReport(input: ApiSchemas['ReportCreate']): Promise<Report> {
  return apiRequest('/api/v1/reports', { method: 'POST', body: input })
}

export function listBlockedUsers(offset = 0): Promise<BlockedUser[]> {
  return apiRequest(`/api/v1/blocks?offset=${offset}&limit=50`)
}

export function blockUser(userId: string): Promise<void> {
  return apiRequest(`/api/v1/users/${userId}/block`, { method: 'POST' })
}

export function unblockUser(userId: string): Promise<void> {
  return apiRequest(`/api/v1/users/${userId}/block`, { method: 'DELETE' })
}

export function listAdminReports(status: string, offset = 0): Promise<Report[]> {
  return apiRequest(`/api/v1/admin/reports?status=${encodeURIComponent(status)}&offset=${offset}&limit=100`)
}

export function updateAdminReport(reportId: string, status: ApiSchemas['ReportStatusUpdate']['status']): Promise<Report> {
  return apiRequest(`/api/v1/admin/reports/${reportId}`, { method: 'PATCH', body: { status } })
}

export function setAdminContentHidden(type: string, id: string, hidden: boolean): Promise<{ hidden: boolean }> {
  return apiRequest(`/api/v1/admin/content/${encodeURIComponent(type)}/${id}?hidden=${hidden}`, { method: 'PATCH' })
}

export function suspendUser(userId: string): Promise<unknown> {
  return apiRequest(`/api/v1/admin/users/${userId}/suspend`, { method: 'POST' })
}

export function unsuspendUser(userId: string): Promise<unknown> {
  return apiRequest(`/api/v1/admin/users/${userId}/unsuspend`, { method: 'POST' })
}

export function getPlatformAdminAccess(): Promise<{ is_platform_admin: boolean }> {
  return apiRequest('/api/v1/platform-admin/access')
}
