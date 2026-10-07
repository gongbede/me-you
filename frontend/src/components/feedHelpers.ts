import type { InfiniteData } from '@tanstack/react-query'
import type { FeedPage } from '../api/social'

export const MAX_POST_LENGTH = 10_000

export function isValidPostContent(value: string): boolean {
  const trimmed = value.trim()
  const characterCount = Array.from(trimmed).length
  return characterCount > 0 && characterCount <= MAX_POST_LENGTH
}

export function updateOptimisticLike(
  previous: InfiniteData<FeedPage> | undefined,
  postId: string,
  liked: boolean,
): InfiniteData<FeedPage> | undefined {
  if (!previous) return previous
  return {
    ...previous,
    pages: previous.pages.map((page) => ({
      ...page,
      items: page.items.map((post) => {
        if (post.id !== postId || post.liked_by_me === liked) return post
        return {
          ...post,
          liked_by_me: liked,
          like_count: Math.max(0, post.like_count + (liked ? 1 : -1)),
        }
      }),
    })),
  }
}

export function relativeTime(timestamp: string, now = Date.now()): string {
  const seconds = Math.round((new Date(timestamp).getTime() - now) / 1000)
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, 'second'],
    [60, 'minute'],
    [24, 'hour'],
    [7, 'day'],
    [4.345, 'week'],
    [12, 'month'],
    [Number.POSITIVE_INFINITY, 'year'],
  ]
  let value = seconds
  let size = Math.abs(seconds)
  let unit: Intl.RelativeTimeFormatUnit = 'second'
  for (const [divisor, candidate] of units) {
    unit = candidate
    if (size < divisor) break
    value = Math.round(value / divisor)
    size = Math.abs(value)
  }
  return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(value, unit)
}