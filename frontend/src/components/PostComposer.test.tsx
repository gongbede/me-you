import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PostComposer } from './PostComposer'
import { MAX_POST_IMAGES, type PostImageLimits } from '../api/media'
import { isValidPostContent, MAX_POST_LENGTH } from './feedHelpers'

describe('PostComposer', () => {
  const imageLimits: PostImageLimits = {
    max_bytes: 100,
    content_types: ['image/jpeg', 'image/png', 'image/webp'],
  }

  it('validates trimmed content and the backend character limit', () => {
    expect(isValidPostContent('  ')).toBe(false)
    expect(isValidPostContent('hello')).toBe(true)
    expect(isValidPostContent('🙂'.repeat(MAX_POST_LENGTH))).toBe(true)
    expect(isValidPostContent('🙂'.repeat(MAX_POST_LENGTH + 1))).toBe(false)
    expect(isValidPostContent('x'.repeat(MAX_POST_LENGTH))).toBe(true)
    expect(isValidPostContent('x'.repeat(MAX_POST_LENGTH + 1))).toBe(false)
  })

  it('keeps posting disabled for blank content and submits trimmed text', async () => {
    const user = userEvent.setup()
    const onPost = vi.fn().mockResolvedValue(undefined)
    render(<PostComposer
      onPost={onPost}
      isPosting={false}
      error={null}
      imageLimits={{ max_bytes: 100, content_types: ['image/jpeg', 'image/png', 'image/webp'] }}
      imageLimitsError={null}
    />)
    const postButton = screen.getByRole('button', { name: 'Post' })
    const composer = screen.getByRole('textbox', { name: 'Share something with your community' })

    expect(postButton).toBeDisabled()
    await user.type(composer, '  hello  ')
    expect(postButton).toBeEnabled()
    await user.click(postButton)
    expect(onPost).toHaveBeenCalledWith('hello', [])
  })

  it('attaches images with alt text and removes them from the draft', async () => {
    const user = userEvent.setup()
    const onPost = vi.fn().mockResolvedValue(undefined)
    const uploadImage = vi.fn(async (file: File) => ({ media_asset_id: file.name, alt_text: '' }))
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn((file: File) => `blob:${file.name}`),
      revokeObjectURL: vi.fn(),
    })
    render(<PostComposer onPost={onPost} isPosting={false} error={null} imageLimits={imageLimits} imageLimitsError={null} uploadImage={uploadImage} />)

    await user.type(screen.getByRole('textbox', { name: 'Share something with your community' }), 'A photo post')
    const file = new File(['image'], 'photo.png', { type: 'image/png' })
    await user.upload(screen.getByLabelText('Add images'), file)
    expect(screen.getByRole('img', { name: 'photo.png' })).toHaveAttribute('src', 'blob:photo.png')
    await user.type(screen.getByRole('textbox', { name: 'Alt text for photo.png' }), 'A red kite')
    await user.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(onPost).toHaveBeenCalledWith('A photo post', [
      { media_asset_id: 'photo.png', alt_text: 'A red kite' },
    ]))
    expect(uploadImage).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('img', { name: 'photo.png' })).not.toBeInTheDocument()
  })

  it('shows per-file validation errors and enforces the image count limit', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn((file: File) => `blob:${file.name}`),
      revokeObjectURL: vi.fn(),
    })
    render(<PostComposer onPost={vi.fn()} isPosting={false} error={null} imageLimits={imageLimits} imageLimitsError={null} />)

    await user.upload(screen.getByLabelText('Add images'), new File(['svg'], 'bad.svg', { type: 'image/svg+xml' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a JPEG, PNG, or WebP image')
    expect(screen.getByRole('button', { name: 'Post' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Remove bad.svg' }))
    const manyImages = Array.from({ length: MAX_POST_IMAGES + 1 }, (_, index) => (
      new File(['image'], `image-${index}.png`, { type: 'image/png' })
    ))
    await user.upload(screen.getByLabelText('Add images'), manyImages)
    expect(screen.getByRole('alert')).toHaveTextContent(`up to ${MAX_POST_IMAGES} images`)
    expect(screen.getAllByRole('img')).toHaveLength(MAX_POST_IMAGES)
  })
})