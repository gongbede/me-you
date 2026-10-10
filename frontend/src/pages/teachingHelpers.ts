import type { ExerciseSubmissionInboxItem } from '../api/education'

export type ReviewFilter = 'ALL' | 'NEEDS_REVIEW' | 'REVIEWED'

export function filterReviewSubmissions(
  submissions: ExerciseSubmissionInboxItem[],
  filter: ReviewFilter,
): ExerciseSubmissionInboxItem[] {
  if (filter === 'NEEDS_REVIEW') return submissions.filter((submission) => submission.reviewed_at === null)
  if (filter === 'REVIEWED') return submissions.filter((submission) => submission.reviewed_at !== null)
  return submissions
}