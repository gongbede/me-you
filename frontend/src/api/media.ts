import { apiRequest, type ApiSchemas } from './client'
import { avatarUploadTransport } from './avatar'

export type PostImageLimits = ApiSchemas['MediaPostImageLimitsResponse']
export type UploadedPostImage = ApiSchemas['PostAttachmentInput']

export const MAX_POST_IMAGES = 4

export interface PostImageUploadTransport {
  createIntent: (input: ApiSchemas['MediaUploadIntentCreate']) => Promise<ApiSchemas['MediaUploadIntentResponse']>
  upload: (
    url: string,
    headers: Record<string, string>,
    file: File,
    onProgress: (percent: number) => void,
  ) => Promise<void>
  complete: (assetId: string) => Promise<ApiSchemas['MediaAssetResponse']>
}

const postImageUploadTransport: PostImageUploadTransport = {
  createIntent: (input) => apiRequest('/api/v1/media/upload-intents', { method: 'POST', body: input }),
  upload: avatarUploadTransport.upload,
  complete: avatarUploadTransport.complete,
}

export function getPostImageLimits(): Promise<PostImageLimits> {
  return apiRequest('/api/v1/media/post-image-limits')
}

export function validatePostImage(
  file: Pick<File, 'type' | 'size'>,
  limits: PostImageLimits,
): string | null {
  if (!limits.content_types.includes(file.type)) return 'Choose a JPEG, PNG, or WebP image.'
  if (file.size < 1 || file.size > limits.max_bytes) {
    return `Choose an image smaller than ${Math.ceil(limits.max_bytes / 1_000_000)} MB.`
  }
  return null
}

export async function uploadPostImage(
  file: File,
  limits: PostImageLimits,
  onProgress: (percent: number) => void = () => undefined,
  transport: PostImageUploadTransport = postImageUploadTransport,
): Promise<UploadedPostImage> {
  const validationError = validatePostImage(file, limits)
  if (validationError) throw new Error(validationError)

  onProgress(0)
  const intent = await transport.createIntent({
    purpose: 'POST_IMAGE',
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
  if (asset.status !== 'READY') throw new Error('The image upload did not complete. Please try again.')
  onProgress(100)
  return { media_asset_id: asset.id, alt_text: '' }
}