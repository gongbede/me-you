import { apiRequest, type ApiSchemas } from './client'

export const MAX_AVATAR_BYTES = 5_000_000
export const AVATAR_CONTENT_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const

export interface AvatarUploadTransport {
  createIntent: (input: ApiSchemas['MediaUploadIntentCreate']) => Promise<ApiSchemas['MediaUploadIntentResponse']>
  upload: (
    url: string,
    headers: Record<string, string>,
    file: File,
    onProgress: (percent: number) => void,
  ) => Promise<void>
  complete: (assetId: string) => Promise<ApiSchemas['MediaAssetResponse']>
  setAvatar: (assetId: string) => Promise<ApiSchemas['ProfileResponse']>
}

export function validateAvatarFile(file: Pick<File, 'type' | 'size'>): string | null {
  if (!(AVATAR_CONTENT_TYPES as readonly string[]).includes(file.type)) {
    return 'Choose a JPEG, PNG, or WebP image.'
  }
  if (file.size < 1 || file.size > MAX_AVATAR_BYTES) {
    return 'Avatar images must be smaller than 5 MB.'
  }
  return null
}

const xhrUpload = (
  url: string,
  headers: Record<string, string>,
  file: File,
  onProgress: (percent: number) => void,
) => new Promise<void>((resolve, reject) => {
  const request = new XMLHttpRequest()
  request.open('PUT', new URL(url, window.location.origin).toString())
  for (const [name, value] of Object.entries(headers)) request.setRequestHeader(name, value)
  request.upload.addEventListener('progress', (event) => {
    if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100))
  })
  request.addEventListener('load', () => {
    if (request.status >= 200 && request.status < 300) resolve()
    else reject(new Error(`Upload failed (${request.status}). Please try again.`))
  })
  request.addEventListener('error', () => reject(new Error('Upload failed. Check your connection and try again.')))
  request.send(file)
})

export const avatarUploadTransport: AvatarUploadTransport = {
  createIntent: (input) => apiRequest('/api/v1/media/upload-intents', { method: 'POST', body: input }),
  upload: xhrUpload,
  complete: (assetId) => apiRequest(`/api/v1/media/${assetId}/complete`, { method: 'POST' }),
  setAvatar: (assetId) => apiRequest('/api/v1/profile/me/avatar', {
    method: 'PUT',
    body: { asset_id: assetId },
  }),
}

export function clearAvatar(): Promise<ApiSchemas['ProfileResponse']> {
  return apiRequest('/api/v1/profile/me/avatar', { method: 'DELETE' })
}

export async function uploadAvatar(
  file: File,
  onProgress: (percent: number) => void = () => undefined,
  transport: AvatarUploadTransport = avatarUploadTransport,
): Promise<ApiSchemas['ProfileResponse']> {
  const validationError = validateAvatarFile(file)
  if (validationError) throw new Error(validationError)

  onProgress(0)
  const intent = await transport.createIntent({
    purpose: 'PROFILE_IMAGE',
    content_type: file.type,
    byte_size: file.size,
    original_filename: file.name,
  })
  await transport.upload(intent.upload_url, intent.required_headers, file, (percent) => {
    onProgress(Math.min(85, 10 + Math.round(percent * 0.75)))
  })
  onProgress(90)
  const asset = await transport.complete(intent.asset.id)
  if (asset.status !== 'READY') throw new Error('The avatar upload did not complete. Please try again.')
  const profile = await transport.setAvatar(asset.id)
  onProgress(100)
  return profile
}