import { apiRequest, apiRequestWithCursor, type ApiSchemas } from './client'

export type Post = ApiSchemas['PostResponse']
export type Comment = ApiSchemas['CommentResponse']
export type FeedPage = ApiSchemas['FeedResponse']
export type PostLike = ApiSchemas['LikeResponse']
export type CommentLike = ApiSchemas['CommentLikeResponse']
export type PostAttachmentInput = ApiSchemas['PostAttachmentInput']
export type FeedMode = 'FOLLOWING' | 'LATEST'

export function getFeed(cursor?: string, mode: FeedMode = 'FOLLOWING'): Promise<FeedPage> {
  const query = new URLSearchParams({ limit: '20' })
  query.set('mode', mode)
  if (cursor) query.set('cursor', cursor)
  return apiRequest(`/api/v1/posts/feed?${query}`)
}

export function getPost(postId: string): Promise<Post> {
  return apiRequest(`/api/v1/posts/${postId}`)
}

export function createPost(
  content: string,
  attachments: PostAttachmentInput[] = [],
): Promise<Post> {
  return apiRequest('/api/v1/posts', {
    method: 'POST',
    body: { content, visibility: 'PUBLIC', attachments } satisfies ApiSchemas['CreatePost'],
  })
}

export function updatePost(postId: string, update: ApiSchemas['UpdatePost']): Promise<Post> {
  return apiRequest(`/api/v1/posts/${postId}`, { method: 'PATCH', body: update })
}

export function deletePost(postId: string): Promise<void> {
  return apiRequest(`/api/v1/posts/${postId}`, { method: 'DELETE' })
}

export function setPostLike(postId: string, liked: boolean): Promise<void | PostLike> {
  return liked
    ? apiRequest(`/api/v1/posts/${postId}/like`, { method: 'POST' })
    : apiRequest(`/api/v1/posts/${postId}/like`, { method: 'DELETE' })
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

export function createComment(
  postId: string,
  content: string,
  parentId?: string,
): Promise<Comment> {
  return apiRequest(`/api/v1/posts/${postId}/comments`, {
    method: 'POST',
    body: { content, parent_id: parentId } satisfies ApiSchemas['CreateComment'],
  })
}

export function updateComment(commentId: string, content: string): Promise<Comment> {
  return apiRequest(`/api/v1/comments/${commentId}`, {
    method: 'PATCH',
    body: { content } satisfies ApiSchemas['UpdateComment'],
  })
}

export function deleteComment(commentId: string): Promise<void> {
  return apiRequest(`/api/v1/comments/${commentId}`, { method: 'DELETE' })
}

export function setCommentLike(
  commentId: string,
  liked: boolean,
): Promise<void | CommentLike> {
  return liked
    ? apiRequest(`/api/v1/comments/${commentId}/like`, { method: 'POST' })
    : apiRequest(`/api/v1/comments/${commentId}/like`, { method: 'DELETE' })
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

export function getUserFollowersPage(
  userId: string,
  cursor?: string,
): Promise<{ items: ApiSchemas['FollowUserResponse'][]; nextCursor: string | null }> {
  return getCursorPage(`/api/v1/users/${userId}/followers`, cursor)
}

export function getUserFollowing(userId: string): Promise<ApiSchemas['FollowUserResponse'][]> {
  return getAllCursorItems(`/api/v1/users/${userId}/following`)
}

export function getUserFollowingPage(
  userId: string,
  cursor?: string,
): Promise<{ items: ApiSchemas['FollowUserResponse'][]; nextCursor: string | null }> {
  return getCursorPage(`/api/v1/users/${userId}/following`, cursor)
}

export function getUserPosts(
  userId: string,
  postType: 'POST' | 'REEL',
  cursor?: string,
): Promise<FeedPage> {
  const query = new URLSearchParams({ post_type: postType, limit: '20' })
  if (cursor) query.set('cursor', cursor)
  return apiRequest(`/api/v1/users/${userId}/posts?${query}`)
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

async function getCursorPage<TItem>(
  path: string,
  cursor?: string,
): Promise<{ items: TItem[]; nextCursor: string | null }> {
  const query = new URLSearchParams({ limit: '50' })
  if (cursor) query.set('cursor', cursor)
  const page = await apiRequestWithCursor<TItem[]>(`${path}?${query}`)
  return { items: page.data, nextCursor: page.nextCursor }
}