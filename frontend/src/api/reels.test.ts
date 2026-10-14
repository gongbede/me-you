import { describe, expect, it, vi } from 'vitest'
import { uploadReel, validateReelFile, type Reel, type ReelLimits, type ReelUploadTransport } from './reels'

const limits: ReelLimits = { content_types: ['video/mp4', 'video/webm'], max_bytes: 4 }

describe('reel upload flow', () => {
  it('validates the backend MIME allowlist and byte limit before requesting an intent', async () => {
    const file = new File(['video'], 'clip.mp4', { type: 'video/mp4' })
    expect(validateReelFile(file, limits)).toContain('smaller than')
    expect(validateReelFile(new File(['ok'], 'clip.mov', { type: 'video/quicktime' }), limits)).toContain('MP4 or WebM')

    const createIntent = vi.fn()
    await expect(uploadReel(file, 'A clip', limits, vi.fn(), {
      createIntent,
      upload: vi.fn(),
      complete: vi.fn(),
      createReel: vi.fn(),
    })).rejects.toThrow('smaller than')
    expect(createIntent).not.toHaveBeenCalled()
  })

  it('runs intent, upload, complete, and reel creation in order', async () => {
    const calls: string[] = []
    const reel = { id: 'reel-id' } as Reel
    const transport: ReelUploadTransport = {
      createIntent: vi.fn(async (): Promise<Awaited<ReturnType<ReelUploadTransport['createIntent']>>> => {
        calls.push('intent')
        return {
          asset: {
            id: 'asset-id',
            byte_size: 2,
            checksum_sha256: null,
            content_type: 'video/mp4',
            created_at: '2026-01-01T00:00:00Z',
            original_filename: 'clip.mp4',
            purpose: 'REEL',
            status: 'UPLOAD_PENDING',
          },
          upload_url: '/upload/token',
          required_headers: { 'Content-Type': 'video/mp4' },
          expires_at: '2026-01-01T00:10:00Z',
        }
      }),
      upload: vi.fn(async (_url, _headers, _file, onProgress) => {
        calls.push('upload')
        onProgress(100)
      }),
      complete: vi.fn(async () => {
        calls.push('complete')
        return { id: 'asset-id', status: 'READY' } as Awaited<ReturnType<ReelUploadTransport['complete']>>
      }),
      createReel: vi.fn(async () => {
        calls.push('create-reel')
        return reel
      }),
    }
    const progress: number[] = []

    await expect(uploadReel(new File(['ok'], 'clip.mp4', { type: 'video/mp4' }), 'A clip', limits, (value) => progress.push(value), transport)).resolves.toBe(reel)

    expect(calls).toEqual(['intent', 'upload', 'complete', 'create-reel'])
    expect(progress.at(-1)).toBe(100)
  })
})