import { apiRequest, apiRequestWithCursor, type ApiSchemas } from './client'

export type Conversation = ApiSchemas['ConversationResponse']
export type Message = ApiSchemas['MessageResponse']
export type ConversationPage = { items: Message[]; nextCursor: string | null }

export function listConversations(): Promise<Conversation[]> {
  return apiRequest('/api/v1/conversations?limit=100')
}

export function getConversation(conversationId: string): Promise<Conversation> {
  return apiRequest(`/api/v1/conversations/${conversationId}`)
}

export function createDirectConversation(targetUserId: string): Promise<Conversation> {
  return apiRequest('/api/v1/conversations/direct', {
    method: 'POST',
    body: { target_user_id: targetUserId },
  })
}

export function createGroupConversation(name: string, memberIds: string[]): Promise<Conversation> {
  return apiRequest('/api/v1/conversations/group', {
    method: 'POST',
    body: { name, member_ids: memberIds },
  })
}

export async function listConversationMessages(conversationId: string, cursor?: string, limit = 30): Promise<ConversationPage> {
  const query = new URLSearchParams({ limit: String(limit) })
  if (cursor) query.set('cursor', cursor)
  const page = await apiRequestWithCursor<Message[]>(`/api/v1/conversations/${conversationId}/messages?${query}`)
  return { items: page.data, nextCursor: page.nextCursor }
}

export function sendConversationMessage(conversationId: string, content: string): Promise<Message> {
  return apiRequest(`/api/v1/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: { content },
  })
}

export function markConversationRead(conversationId: string): Promise<ApiSchemas['ReadStateResponse']> {
  return apiRequest(`/api/v1/conversations/${conversationId}/read`, { method: 'POST' })
}

export function editMessage(messageId: string, content: string): Promise<Message> {
  return apiRequest(`/api/v1/messages/${messageId}`, { method: 'PATCH', body: { content } })
}

export function deleteMessage(messageId: string): Promise<void> {
  return apiRequest(`/api/v1/messages/${messageId}`, { method: 'DELETE' })
}