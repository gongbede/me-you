import { apiRequest, apiRequestWithCursor, type ApiSchemas } from './client'

export type Post = ApiSchemas['PostResponse']
export type Comment = ApiSchemas['CommentResponse']
export type FeedPage = ApiSchemas['FeedResponse']
export type PostLike = ApiSchemas['LikeResponse']

export function getFeed(cursor?: string): Promise<FeedPage> {
  const query = new URLSearchParams({ limit: '20' })
  if (cursor) query.set('cursor', cursor)
  return apiRequest(`/api/v1/posts/feed?${query}`)
}

export function createPost(content: string): Promise<Post> {
  return apiRequest('/api/v1/posts', {
    method: 'POST',
    body: { content, visibility: 'PUBLIC' },
  })
}

export function deletePost(postId: string): Promise<void> {
  return apiRequest(`/api/v1/posts/${postId}`, { method: 'DELETE' })
}

export function setPostLike(postId: string, liked: boolean): Promise<void | PostLike> {
  return liked
    ? apiRequest(`/api/v1/posts/${postId}/like`, { method: 'POST' })
    : apiRequest(`/api/v1/posts/${postId}/like`, { method: 'DELETE' })
}

export async function getPostEngagement(postId: string): Promise<{
  likeCount: number
  commentCount: number
  likedByUserIds: Set<string>
}> {
  const [likes, comments] = await Promise.all([
    getAllCursorItems<PostLike>(`/api/v1/posts/${postId}/likes`),
    getAllCursorItems<Comment>(`/api/v1/posts/${postId}/comments`),
  ])
  return {
    likeCount: likes.length,
    commentCount: comments.length,
    likedByUserIds: new Set(likes.map((like) => like.user_id)),
  }
}

export function getCommentsPage(postId: string, cursor?: string): Promise<{
  items: Comment[]
  nextCursor: string | null
}> {
  const query = new URLSearchParams({ limit: '50' })
  if (cursor) query.set('cursor', cursor)
  return apiRequestWithCursor<Comment[]>(
    `/api/v1/posts/${postId}/comments?${query}`,
  ).then(({ data, nextCursor }) => ({ items: data, nextCursor }))
}

export function createComment(postId: string, content: string): Promise<Comment> {
  return apiRequest(`/api/v1/posts/${postId}/comments`, {
    method: 'POST',
    body: { content },
  })
}

export function deleteComment(commentId: string): Promise<void> {
  return apiRequest(`/api/v1/comments/${commentId}`, { method: 'DELETE' })
}

export function getPublicProfile(userId: string): Promise<ApiSchemas['ProfileDiscoveryResponse']> {
  return apiRequest(`/api/v1/users/${userId}/profile`)
}

export function followUser(userId: string): Promise<ApiSchemas['FollowUserResponse']> {
  return apiRequest(`/api/v1/users/${userId}/follow`, { method: 'POST' })
}

export function unfollowUser(userId: string): Promise<void> {
  return apiRequest(`/api/v1/users/${userId}/follow`, { method: 'DELETE' })
}

export function getUserFollowers(userId: string): Promise<ApiSchemas['FollowUserResponse'][]> {
  return getAllCursorItems(`/api/v1/users/${userId}/followers`)
}

async function getAllCursorItems<TItem>(path: string): Promise<TItem[]> {
  const items: TItem[] = []
  let cursor: string | null = null

  do {
    const query = new URLSearchParams({ limit: '100' })
    if (cursor) query.set('cursor', cursor)
    const page = await apiRequestWithCursor<TItem[]>(`${path}?${query}`)
    items.push(...page.data)
    cursor = page.nextCursor
  } while (cursor)

  return items
}