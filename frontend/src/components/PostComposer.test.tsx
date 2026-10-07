import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PostComposer } from './PostComposer'
import { isValidPostContent, MAX_POST_LENGTH } from './feedHelpers'

describe('PostComposer', () => {
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
    render(<PostComposer onPost={onPost} isPosting={false} error={null} />)
    const postButton = screen.getByRole('button', { name: 'Post' })
    const composer = screen.getByRole('textbox', { name: 'Share something with your community' })

    expect(postButton).toBeDisabled()
    await user.type(composer, '  hello  ')
    expect(postButton).toBeEnabled()
    await user.click(postButton)
    expect(onPost).toHaveBeenCalledWith('hello')
  })
})