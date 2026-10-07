export const MAX_POST_LENGTH = 10_000

export interface Engagement {
  likeCount: number
  commentCount: number
  likedByUserIds: Set<string>
}

export function isValidPostContent(value: string): boolean {
  const trimmed = value.trim()
  const characterCount = Array.from(trimmed).length
  return characterCount > 0 && characterCount <= MAX_POST_LENGTH
}

export function updateOptimisticLike(
  previous: Engagement | undefined,
  userId: string,
  liked: boolean,
): Engagement | undefined {
  if (!previous) return previous
  const wasLiked = previous.likedByUserIds.has(userId)
  if (wasLiked === liked) return previous
  const likedByUserIds = new Set(previous.likedByUserIds)
  if (liked) likedByUserIds.add(userId)
  else likedByUserIds.delete(userId)
  return { ...previous, likeCount: previous.likeCount + (liked ? 1 : -1), likedByUserIds }
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