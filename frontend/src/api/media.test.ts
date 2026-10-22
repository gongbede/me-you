import { describe, expect, it, vi } from 'vitest'

import {
  uploadPostImage,
  validatePostImage,
  type PostImageUploadTransport,
} from './media'

const limits = {
  max_bytes: 100,
  content_types: ['image/jpeg', 'image/png', 'image/webp'],
}

describe('post image upload', () => {
  it('validates the server MIME allowlist and byte cap', () => {
    expect(validatePostImage(new File(['ok'], 'photo.png', { type: 'image/png' }), limits)).toBeNull()
    expect(validatePostImage(new File(['x'], 'photo.svg', { type: 'image/svg+xml' }), limits)).toContain('JPEG, PNG, or WebP')
    expect(validatePostImage(new File([new Uint8Array(101)], 'large.png', { type: 'image/png' }), limits)).toContain('1 MB')
  })

  it('uploads, completes, and reports progress with an injectable transport', async () => {
    const calls: string[] = []
    const progress: number[] = []
    const transport: PostImageUploadTransport = {
      createIntent: vi.fn(async (input) => {
        calls.push(`intent:${input.purpose}`)
        return {
          asset: {
            id: 'asset-id', purpose: 'POST_IMAGE' as const, status: 'UPLOAD_PENDING' as const,
            content_type: 'image/png', byte_size: 2, original_filename: 'photo.png',
            checksum_sha256: null, created_at: '2026-01-01T00:00:00Z', institution_id: null,
          },
          upload_url: '/upload/token', required_headers: { 'Content-Type': 'image/png' },
          expires_at: '2026-01-01T00:10:00Z',
        }
      }),
      upload: vi.fn(async (_url, _headers, _file, onProgress) => {
        calls.push('upload')
        onProgress(50)
      }),
      complete: vi.fn(async () => {
        calls.push('complete')
        return {
          id: 'asset-id', purpose: 'POST_IMAGE' as const, status: 'READY' as const,
          content_type: 'image/png', byte_size: 2, original_filename: 'photo.png',
          checksum_sha256: null, created_at: '2026-01-01T00:00:00Z', institution_id: null,
        }
      }),
    }

    const result = await uploadPostImage(
      new File(['ok'], 'photo.png', { type: 'image/png' }),
      limits,
      (value) => progress.push(value),
      transport,
    )

    expect(result).toEqual({ media_asset_id: 'asset-id', alt_text: '' })
    expect(calls).toEqual(['intent:POST_IMAGE', 'upload', 'complete'])
    expect(progress).toEqual([0, 8, 45, 88, 100])
  })
})