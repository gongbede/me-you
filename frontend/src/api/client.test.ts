import { describe, expect, it } from 'vitest'
import { ApiError, getFriendlyErrorMessage } from './client'

describe('API error messages', () => {
  it('uses Retry-After to give a friendly 429 message', () => {
    const message = getFriendlyErrorMessage(
      new ApiError('Too many requests', 429, '17'),
    )
    expect(message).toBe('You’re moving quickly. Please try again in 17 seconds.')
  })

  it('uses a friendly fallback when Retry-After is not numeric', () => {
    const message = getFriendlyErrorMessage(new ApiError('Busy', 429, null))
    expect(message).toContain('try again in a little while')
  })
})