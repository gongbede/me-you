import { apiRequest, apiRequestWithCursor, type ApiSchemas } from './client'
import { avatarUploadTransport, type AvatarUploadTransport } from './avatar'
import type { Post } from './social'

export type Reel = Post & { post_type: 'REEL'; media_asset_id: string; video_url: string }
export type ReelLimits = ApiSchemas['MediaReelLimitsResponse']
export type ReelFeedPage = Omit<ApiSchemas['FeedResponse'], 'items'> & { items: Reel[] }

export function getReelLimits(): Promise<ReelLimits> {
  return apiRequest('/api/v1/media/reel-limits')
}

export async function getReelsPage(cursor?: string, limit = 10): Promise<ReelFeedPage> {
  const query = new URLSearchParams({ limit: String(limit) })
  if (cursor) query.set('cursor', cursor)
  return apiRequest(`/api/v1/reels/feed?${query}`)
}

export function createReelRecord(mediaAssetId: string, content: string): Promise<Reel> {
  return apiRequest('/api/v1/reels', {
    method: 'POST',
    body: { media_asset_id: mediaAssetId, content, visibility: 'PUBLIC' },
  })
}

export function deleteReel(reelId: string): Promise<void> {
  return apiRequest(`/api/v1/reels/${reelId}`, { method: 'DELETE' })
}

export function validateReelFile(file: Pick<File, 'type' | 'size'>, limits: ReelLimits): string | null {
  if (!limits.content_types.includes(file.type)) return 'Choose an MP4 or WebM video.'
  if (file.size < 1 || file.size > limits.max_bytes) {
    return `Choose a video smaller than ${Math.floor(limits.max_bytes / 1_000_000)} MB.`
  }
  return null
}

export interface ReelUploadTransport extends Pick<AvatarUploadTransport, 'createIntent' | 'upload' | 'complete'> {
  createReel: (assetId: string, caption: string) => Promise<Reel>
}

const reelUploadTransport: ReelUploadTransport = {
  createIntent: avatarUploadTransport.createIntent,
  upload: avatarUploadTransport.upload,
  complete: avatarUploadTransport.complete,
  createReel: createReelRecord,
}

export async function uploadReel(
  file: File,
  caption: string,
  limits: ReelLimits,
  onProgress: (percent: number) => void = () => undefined,
  transport: ReelUploadTransport = reelUploadTransport,
): Promise<Reel> {
  const validationError = validateReelFile(file, limits)
  if (validationError) throw new Error(validationError)
  const cleanCaption = caption.trim()
  if (!cleanCaption || cleanCaption.length > 10_000) throw new Error('Add a caption up to 10,000 characters.')

  onProgress(0)
  const intent = await transport.createIntent({
    purpose: 'REEL',
    content_type: file.type,
    byte_size: file.size,
    original_filename: file.name,
  })
  onProgress(8)
  await transport.upload(intent.upload_url, intent.required_headers, file, (percent) => {
    onProgress(Math.min(82, 8 + Math.round(percent * 0.74)))
  })
  onProgress(88)
  const asset = await transport.complete(intent.asset.id)
  if (asset.status !== 'READY') throw new Error('The video upload did not complete. Please try again.')
  onProgress(94)
  const reel = await transport.createReel(asset.id, cleanCaption)
  onProgress(100)
  return reel
}

export async function getReelsCursorPage(cursor?: string): Promise<{ items: Reel[]; nextCursor: string | null }> {
  const query = new URLSearchParams({ limit: '10' })
  if (cursor) query.set('cursor', cursor)
  const page = await apiRequestWithCursor<Reel[]>(`/api/v1/reels/feed?${query}`)
  return { items: page.data, nextCursor: page.nextCursor }
}