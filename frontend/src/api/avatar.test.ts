import { describe, expect, it, vi } from 'vitest'
import {
  MAX_AVATAR_BYTES,
  uploadAvatar,
  validateAvatarFile,
  type AvatarUploadTransport,
} from './avatar'

const profile = {
  user_id: 'user-id',
  display_name: 'Learner',
  bio: null,
  profile_picture_url: '/api/v1/media/local-download/signed-token',
  location: null,
  website: null,
  visibility: 'NETWORK' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('avatar upload flow', () => {
  it('validates the backend MIME allowlist and byte limit', () => {
    expect(validateAvatarFile(new File(['ok'], 'avatar.jpg', { type: 'image/jpeg' }))).toBeNull()
    expect(validateAvatarFile(new File(['ok'], 'avatar.gif', { type: 'image/gif' }))).toContain('JPEG, PNG, or WebP')
    const oversized = new File([new Uint8Array(MAX_AVATAR_BYTES + 1)], 'large.png', { type: 'image/png' })
    expect(validateAvatarFile(oversized)).toContain('5 MB')
  })

  it('runs intent, upload, complete, and set-avatar in order', async () => {
    const calls: string[] = []
    const transport: AvatarUploadTransport = {
      createIntent: vi.fn(async () => {
        calls.push('intent')
        return {
          asset: {
            id: 'asset-id',
            purpose: 'PROFILE_IMAGE' as const,
            status: 'UPLOAD_PENDING' as const,
            content_type: 'image/png',
            byte_size: 2,
            original_filename: 'avatar.png',
            checksum_sha256: null,
            created_at: '2026-01-01T00:00:00Z',
            institution_id: null,
          },
          upload_url: '/api/v1/media/local-upload/token',
          required_headers: { 'Content-Type': 'image/png' },
          expires_at: '2026-01-01T00:10:00Z',
        }
      }),
      upload: vi.fn(async (_url, _headers, _file, onProgress) => {
        calls.push('upload')
        onProgress(100)
      }),
      complete: vi.fn(async () => {
        calls.push('complete')
        return {
          id: 'asset-id',
          purpose: 'PROFILE_IMAGE' as const,
          status: 'READY' as const,
          content_type: 'image/png',
          byte_size: 2,
          original_filename: 'avatar.png',
          checksum_sha256: null,
          created_at: '2026-01-01T00:00:00Z',
          institution_id: null,
        }
      }),
      setAvatar: vi.fn(async () => {
        calls.push('set-avatar')
        return profile
      }),
    }

    const result = await uploadAvatar(new File(['ok'], 'avatar.png', { type: 'image/png' }), vi.fn(), transport)
    expect(result).toEqual(profile)
    expect(calls).toEqual(['intent', 'upload', 'complete', 'set-avatar'])
    expect(transport.upload).toHaveBeenCalledWith(
      '/api/v1/media/local-upload/token',
      { 'Content-Type': 'image/png' },
      expect.any(File),
      expect.any(Function),
    )
  })
})