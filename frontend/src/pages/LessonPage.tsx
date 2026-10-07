import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, LoaderCircle, Send } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import {
  getLesson,
  getLessonProgress,
  listExercises,
  listExerciseSubmissions,
  setLessonProgress,
  submitExercise,
  type Exercise,
  type LessonProgress,
} from '../api/education'

function LessonExercise({ exercise }: { exercise: Exercise }) {
  const queryClient = useQueryClient()
  const [answer, setAnswer] = useState('')
  const submissionsQuery = useQuery({
    queryKey: ['education', 'exercise-submissions', exercise.id],
    queryFn: () => listExerciseSubmissions(exercise.id),
  })
  const submissionMutation = useMutation({
    mutationFn: (value: string) => {
      const nextAttempt = (submissionsQuery.data?.reduce((max, item) => Math.max(max, item.attempt_number), 0) ?? 0) + 1
      return submitExercise(exercise.id, nextAttempt, value)
    },
    onSuccess: async () => {
      setAnswer('')
      await queryClient.invalidateQueries({ queryKey: ['education', 'exercise-submissions', exercise.id] })
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = answer.trim()
    if (value) submissionMutation.mutate(value)
  }

  return (
    <article className="learning-exercise">
      <div className="learning-exercise__heading"><span className="learning-kicker">{exercise.exercise_type} · {exercise.position + 1}</span><h3>{exercise.title}</h3></div>
      <p>{exercise.instructions}</p>
      {submissionsQuery.isPending ? <p className="learning-loading" role="status">Loading your attempts…</p> : submissionsQuery.isError ? (
        <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(submissionsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void submissionsQuery.refetch()}>Retry</button></div>
      ) : <>
        {submissionsQuery.data.length > 0 && <ol className="learning-attempt-list">
          {submissionsQuery.data.map((submission) => <li key={submission.id}>
            <div className="learning-attempt-meta"><strong>Attempt {submission.attempt_number}</strong><span className="status-label">{submission.reviewed_at ? 'Reviewed' : 'Submitted'}</span><time dateTime={submission.submitted_at}>{new Date(submission.submitted_at).toLocaleDateString()}</time></div>
            <p>{submission.answer_text}</p>
            {submission.feedback && <blockquote><strong>Teacher feedback</strong><span>{submission.feedback}</span></blockquote>}
          </li>)}
        </ol>}
        <form className="learning-submission-form" onSubmit={submit}>
          <label className="field" htmlFor={`answer-${exercise.id}`}><span>Your response</span><textarea id={`answer-${exercise.id}`} rows={3} maxLength={50000} value={answer} onChange={(event) => setAnswer(event.currentTarget.value)} placeholder="Write a short response…" /></label>
          <button className="button button--outline" type="submit" disabled={!answer.trim() || submissionMutation.isPending}>{submissionMutation.isPending ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}{submissionMutation.isPending ? 'Submitting…' : 'Submit attempt'}</button>
        </form>
        {submissionMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(submissionMutation.error)}</p>}
      </>}
    </article>
  )
}

export function LessonPage() {
  const { lessonId = '' } = useParams()
  const queryClient = useQueryClient()
  const lessonQuery = useQuery({ queryKey: ['education', 'lesson', lessonId], queryFn: () => getLesson(lessonId), enabled: Boolean(lessonId) })
  const progressKey = ['education', 'lesson-progress', lessonId] as const
  const progressQuery = useQuery({ queryKey: progressKey, queryFn: () => getLessonProgress(lessonId), enabled: Boolean(lessonQuery.data) })
  const exercisesQuery = useQuery({ queryKey: ['education', 'lesson-exercises', lessonId], queryFn: () => listExercises(lessonId), enabled: Boolean(lessonQuery.data) })
  const progressMutation = useMutation({
    mutationFn: (completed: boolean) => setLessonProgress(lessonId, completed),
    onMutate: async (completed) => {
      await queryClient.cancelQueries({ queryKey: progressKey })
      const previous = queryClient.getQueryData<LessonProgress | null>(progressKey)
      const now = new Date().toISOString()
      queryClient.setQueryData<LessonProgress | null>(progressKey, previous
        ? { ...previous, completed, completed_at: completed ? now : null, updated_at: now }
        : { id: 'optimistic-progress', student_id: '', lesson_id: lessonId, completed, completed_at: completed ? now : null, created_at: now, updated_at: now })
      return { previous }
    },
    onError: (_error, _completed, context) => {
      if (context) queryClient.setQueryData(progressKey, context.previous)
    },
    onSuccess: (progress) => queryClient.setQueryData(progressKey, progress),
    onSettled: (_data, _error, _completed, _context, mutationContext) => {
      const courseId = lessonQuery.data?.course_id
      if (courseId) void mutationContext.client.invalidateQueries({ queryKey: ['education', 'course-lessons', courseId] })
    },
  })

  if (lessonQuery.isPending) return <p className="learning-loading" role="status">Loading lesson…</p>
  if (lessonQuery.isError) return <div className="page-state page-state--error" role="alert"><h1>Lesson unavailable</h1><p>{getFriendlyErrorMessage(lessonQuery.error)} Published lessons require an active student enrollment.</p><Link className="button button--outline" to="/my-courses"><ArrowLeft size={16} aria-hidden="true" /> My courses</Link></div>
  const lesson = lessonQuery.data
  const progress = progressQuery.data

  return (
    <div className="page-stack learning-page">
      <Link className="learning-back-link" to={`/courses/${lesson.course_id}`}><ArrowLeft size={16} aria-hidden="true" /> Back to course</Link>
      <article className="learning-lesson-content">
        <span className="eyebrow">LESSON {lesson.position + 1}</span>
        <h1>{lesson.title}</h1>
        <div className="learning-rich-text">{lesson.content}</div>
        {progressQuery.isPending ? <p className="learning-loading" role="status">Checking your progress…</p> : progressQuery.isError ? (
          <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(progressQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void progressQuery.refetch()}>Retry progress</button></div>
        ) : <button className={`button ${progress?.completed ? 'button--outline' : 'button--primary'}`} type="button" aria-pressed={Boolean(progress?.completed)} disabled={progressMutation.isPending || Boolean(progress?.completed)} onClick={() => progressMutation.mutate(true)}>{progressMutation.isPending ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : <Check size={16} aria-hidden="true" />}{progressMutation.isPending ? 'Saving…' : progress?.completed ? 'Lesson done' : 'Mark as done'}</button>}
        {progressMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(progressMutation.error)} Your progress was restored; please retry.</p>}
      </article>

      <section className="learning-section" aria-labelledby="exercises-heading">
        <div className="learning-section__heading"><div><h2 id="exercises-heading">Exercises</h2><p>Submit written attempts and return to them after review.</p></div></div>
        {exercisesQuery.isPending ? <p className="learning-loading" role="status">Loading exercises…</p> : exercisesQuery.isError ? (
          <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(exercisesQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void exercisesQuery.refetch()}>Retry</button></div>
        ) : exercisesQuery.data.length === 0 ? <p className="learning-empty learning-empty--compact">No exercises for this lesson yet.</p> : <div className="learning-exercise-list">{exercisesQuery.data.map((exercise) => <LessonExercise key={exercise.id} exercise={exercise} />)}</div>}
      </section>
    </div>
  )
}