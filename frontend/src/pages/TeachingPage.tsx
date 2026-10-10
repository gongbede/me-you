import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpen, CircleAlert, ClipboardList, Clock3, LoaderCircle, Plus, Save, Trash2, UserRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { ApiError, getFriendlyErrorMessage } from '../api/client'
import {
  createLesson,
  createExercise,
  deleteExercise,
  deleteLesson,
  getCoursePendingReviewCount,
  getCourseLessons,
  getLesson,
  getTeachingCourses,
  listExercises,
  listCourseExerciseSubmissions,
  reviewExerciseSubmission,
  updateExercise,
  updateLesson,
  type Course,
  type Exercise,
  type ExerciseInput,
  type ExerciseSubmissionInboxItem,
  type Lesson,
  type LessonInput,
} from '../api/education'
import { filterReviewSubmissions, type ReviewFilter } from './teachingHelpers'

const lessonQueryKey = (courseId: string) => ['teaching', 'lessons', courseId] as const

function learningError(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) {
    return 'You do not have teaching access to this course.'
  }
  if (error instanceof ApiError && error.status === 404) {
    return 'This course or lesson is no longer available.'
  }
  return getFriendlyErrorMessage(error)
}

export function LessonForm({
  lesson,
  isSaving,
  onCancel,
  onSave,
}: {
  lesson?: Lesson
  isSaving: boolean
  onCancel?: () => void
  onSave: (value: LessonInput) => Promise<void>
}) {
  const [title, setTitle] = useState(lesson?.title ?? '')
  const [content, setContent] = useState(lesson?.content ?? '')
  const [position, setPosition] = useState(String(lesson?.position ?? 0))
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleanTitle = title.trim()
    const cleanContent = content.trim()
    const numericPosition = Number(position)
    if (!cleanTitle || !cleanContent || !Number.isInteger(numericPosition) || numericPosition < 0) {
      setError('Add a title and content, and use an order of 0 or greater.')
      return
    }
    setError(null)
    try {
      await onSave({ title: cleanTitle, content: cleanContent, position: numericPosition, is_published: lesson?.is_published ?? false })
    } catch {
      setError('We could not save this lesson. Please try again.')
    }
  }

  return (
    <form className="teaching-form" onSubmit={(event) => void submit(event)} noValidate>
      <div className="field">
        <label htmlFor="lesson-title">Title</label>
        <input id="lesson-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={300} required />
        <span className="teaching-form__limit">{title.length}/300</span>
      </div>
      <div className="field">
        <label htmlFor="lesson-content">Content</label>
        <textarea id="lesson-content" value={content} onChange={(event) => setContent(event.target.value)} maxLength={50000} rows={7} required />
        <span className="teaching-form__limit">{content.length}/50,000</span>
      </div>
      <div className="field teaching-form__order">
        <label htmlFor="lesson-position">Order</label>
        <input id="lesson-position" type="number" min={0} step={1} value={position} onChange={(event) => setPosition(event.target.value)} required />
      </div>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="teaching-actions">
        <button className="button button--primary" type="submit" disabled={isSaving}>
          {isSaving ? <LoaderCircle className="spin" size={17} aria-hidden="true" /> : <Save size={17} aria-hidden="true" />}
          {isSaving ? 'Saving…' : lesson ? 'Save changes' : 'Create draft'}
        </button>
        {onCancel && <button className="button button--outline" type="button" onClick={onCancel} disabled={isSaving}>Cancel</button>}
      </div>
    </form>
  )
}

function TeachingHome({ courses, isLoading, error }: { courses: Course[]; isLoading: boolean; error: unknown }) {
  const reviewCounts = useQueries({
    queries: courses.map((course) => ({
      queryKey: ['teaching', 'pending-reviews', course.id],
      queryFn: () => getCoursePendingReviewCount(course.id),
    })),
  })
  if (isLoading) return <div className="page-state" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Loading your courses…</div>
  if (error) return <div className="page-state page-state--error" role="alert"><CircleAlert aria-hidden="true" /><h2>Teaching area unavailable</h2><p>{learningError(error)}</p></div>

  return (
    <div className="page-stack">
      <section className="page-heading-row teaching-heading">
        <div><span className="eyebrow">YOUR CLASSROOMS</span><h1>Teaching</h1><p>Courses assigned to you.</p></div>
      </section>
      {courses.length === 0 ? (
        <section className="teaching-empty" aria-labelledby="teaching-empty-title">
          <BookOpen size={27} aria-hidden="true" />
          <h2 id="teaching-empty-title">No courses assigned yet</h2>
          <p>Courses appear here after a school administrator assigns you.</p>
        </section>
      ) : (
        <div className="teaching-course-list" aria-label="Courses you teach">
          {courses.map((course, index) => (
            <Link className="teaching-course" key={course.id} to={`/teaching/courses/${course.id}`}>
              <span className="teaching-course__icon"><BookOpen size={21} aria-hidden="true" /></span>
              <span className="teaching-course__copy"><strong>{course.name}</strong><small>{course.code}</small></span>
              <span className="teaching-course__meta">
                Students: unavailable · Awaiting review: {reviewCounts[index]?.isPending ? '…' : reviewCounts[index]?.isError ? 'unavailable' : reviewCounts[index]?.data ?? 0}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

function CourseLessons({ courseId }: { courseId: string }) {
  const queryClient = useQueryClient()
  const coursesQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses })
  const course = coursesQuery.data?.find((item) => item.id === courseId)
  const lessonsQuery = useQuery({
    queryKey: lessonQueryKey(courseId),
    queryFn: () => getCourseLessons(courseId),
    enabled: Boolean(course),
  })
  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const refreshLessons = async () => queryClient.invalidateQueries({ queryKey: lessonQueryKey(courseId) })
  const createMutation = useMutation({
    mutationFn: (value: LessonInput) => createLesson(courseId, value),
    onSuccess: async () => { setCreating(false); await refreshLessons() },
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: Partial<LessonInput> }) => updateLesson(id, updates),
    onSuccess: async () => { setEditingId(null); await refreshLessons() },
  })
  const deleteMutation = useMutation({
    mutationFn: deleteLesson,
    onSuccess: refreshLessons,
  })

  if (coursesQuery.isPending) return <div className="page-state" role="status">Loading course…</div>
  if (coursesQuery.error) return <div className="page-state page-state--error" role="alert"><h2>Course unavailable</h2><p>{learningError(coursesQuery.error)}</p></div>
  if (!course) return <div className="page-state page-state--error" role="alert"><h2>Course unavailable</h2><p>You do not have teaching access to this course.</p></div>

  const isSaving = createMutation.isPending || updateMutation.isPending
  async function saveLesson(value: LessonInput, lessonId?: string) {
    setActionError(null)
    try {
      if (lessonId) await updateMutation.mutateAsync({ id: lessonId, updates: value })
      else await createMutation.mutateAsync(value)
    } catch (error) {
      setActionError(learningError(error))
      throw error
    }
  }

  async function togglePublished(lesson: Lesson) {
    const nextState = !lesson.is_published
    const confirmation = nextState ? 'Publish this lesson for enrolled students?' : 'Unpublish this lesson? Students will no longer see it.'
    if (!window.confirm(confirmation)) return
    setActionError(null)
    try {
      await updateMutation.mutateAsync({ id: lesson.id, updates: { is_published: nextState } })
    } catch (error) {
      setActionError(learningError(error))
    }
  }

  async function removeLesson(lesson: Lesson) {
    if (!window.confirm(`Delete “${lesson.title}”? This cannot be undone.`)) return
    setActionError(null)
    try {
      await deleteMutation.mutateAsync(lesson.id)
    } catch (error) {
      setActionError(learningError(error))
    }
  }

  return (
    <div className="page-stack">
      <Link className="teaching-back" to="/teaching"><ArrowLeft size={17} aria-hidden="true" /> All courses</Link>
      <section className="page-heading-row teaching-heading">
        <div><span className="eyebrow">{course.code}</span><h1>{course.name}</h1><p>Manage lesson content and visibility.</p></div>
        <div className="teaching-actions">
          <Link className="button button--outline" to={`/teaching/courses/${course.id}/reviews`}><ClipboardList size={17} aria-hidden="true" /> Review inbox</Link>
          {!creating && <button className="button button--primary" type="button" onClick={() => { setActionError(null); setCreating(true) }}><Plus size={18} aria-hidden="true" /> New lesson</button>}
        </div>
      </section>
      {actionError && <div className="form-alert" role="alert"><CircleAlert size={18} aria-hidden="true" />{actionError}</div>}
      {creating && <section className="teaching-editor" aria-labelledby="lesson-create-title"><h2 id="lesson-create-title">New lesson</h2><LessonForm isSaving={isSaving} onCancel={() => setCreating(false)} onSave={(value) => saveLesson(value)} /></section>}
      {lessonsQuery.isPending ? (
        <div className="page-state" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Loading lessons…</div>
      ) : lessonsQuery.error ? (
        <div className="page-state page-state--error" role="alert"><h2>Lessons unavailable</h2><p>{learningError(lessonsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void lessonsQuery.refetch()}>Try again</button></div>
      ) : lessonsQuery.data.length === 0 && !creating ? (
        <section className="teaching-empty" aria-labelledby="lesson-empty-title"><BookOpen size={27} aria-hidden="true" /><h2 id="lesson-empty-title">No lessons yet</h2><p>Start with a draft. You can publish it when it is ready.</p><button className="button button--primary" type="button" onClick={() => setCreating(true)}><Plus size={18} aria-hidden="true" /> Create first lesson</button></section>
      ) : (
        <div className="lesson-list" aria-label="Course lessons">
          {lessonsQuery.data.map((lesson) => (
            <article className="lesson-row" key={lesson.id}>
              {editingId === lesson.id ? (
                <div className="lesson-row__editor"><h2>Edit lesson</h2><LessonForm lesson={lesson} isSaving={isSaving} onCancel={() => setEditingId(null)} onSave={(value) => saveLesson(value, lesson.id)} /></div>
              ) : (
                <>
                  <div className="lesson-row__main"><span className={`lesson-badge ${lesson.is_published ? 'lesson-badge--published' : ''}`}>{lesson.is_published ? 'Published' : 'Draft'}</span><h2>{lesson.title}</h2><p>Order {lesson.position}</p></div>
                  <div className="teaching-actions lesson-row__actions">
                    <Link className="button button--outline" to={`/teaching/lessons/${lesson.id}`}><ClipboardList size={16} aria-hidden="true" /> Exercises</Link>
                    <button className="button button--outline" type="button" disabled={updateMutation.isPending} onClick={() => { setActionError(null); setEditingId(lesson.id) }}>Edit</button>
                    <button className="button button--outline" type="button" disabled={updateMutation.isPending} onClick={() => void togglePublished(lesson)}>{lesson.is_published ? 'Unpublish' : 'Publish'}</button>
                    <button className="icon-button icon-button--danger" type="button" aria-label={`Delete ${lesson.title}`} disabled={deleteMutation.isPending} onClick={() => void removeLesson(lesson)}><Trash2 size={18} aria-hidden="true" /></button>
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

const exerciseQueryKey = (lessonId: string) => ['teaching', 'exercises', lessonId] as const

export function ExerciseForm({
  exercise,
  isSaving,
  onCancel,
  onSave,
}: {
  exercise?: Exercise
  isSaving: boolean
  onCancel?: () => void
  onSave: (value: ExerciseInput) => Promise<void>
}) {
  const [title, setTitle] = useState(exercise?.title ?? '')
  const [instructions, setInstructions] = useState(exercise?.instructions ?? '')
  const [position, setPosition] = useState(String(exercise?.position ?? 0))
  const [exerciseType, setExerciseType] = useState<ExerciseInput['exercise_type']>(exercise?.exercise_type ?? 'WRITTEN')
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleanTitle = title.trim()
    const cleanInstructions = instructions.trim()
    const numericPosition = Number(position)
    if (!cleanTitle || cleanTitle.length > 200 || !cleanInstructions || !Number.isInteger(numericPosition) || numericPosition < 0) {
      setError('Add a title and instructions, and use an order of 0 or greater.')
      return
    }
    setError(null)
    try {
      await onSave({
        title: cleanTitle,
        instructions: cleanInstructions,
        position: numericPosition,
        exercise_type: exerciseType,
        is_published: exercise?.is_published ?? false,
      })
    } catch {
      setError('We could not save this exercise. Please try again.')
    }
  }

  return (
    <form className="teaching-form" onSubmit={(event) => void submit(event)} noValidate>
      <div className="field">
        <label htmlFor="exercise-title">Title</label>
        <input id="exercise-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} required />
        <span className="teaching-form__limit">{title.length}/200</span>
      </div>
      <div className="field">
        <label htmlFor="exercise-instructions">Instructions</label>
        <textarea id="exercise-instructions" value={instructions} onChange={(event) => setInstructions(event.target.value)} maxLength={20000} rows={6} required />
        <span className="teaching-form__limit">{instructions.length}/20,000</span>
      </div>
      <div className="teaching-form__grid">
        <div className="field teaching-form__order">
          <label htmlFor="exercise-position">Order</label>
          <input id="exercise-position" type="number" min={0} step={1} value={position} onChange={(event) => setPosition(event.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="exercise-type">Type</label>
          <select id="exercise-type" value={exerciseType} onChange={(event) => setExerciseType(event.target.value as ExerciseInput['exercise_type'])}>
            <option value="PRACTICE">Practice</option>
            <option value="WRITTEN">Written</option>
            <option value="PROJECT">Project</option>
            <option value="OTHER">Other</option>
          </select>
        </div>
      </div>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="teaching-actions">
        <button className="button button--primary" type="submit" disabled={isSaving}>
          {isSaving ? <LoaderCircle className="spin" size={17} aria-hidden="true" /> : <Save size={17} aria-hidden="true" />}
          {isSaving ? 'Saving…' : exercise ? 'Save changes' : 'Create draft'}
        </button>
        {onCancel && <button className="button button--outline" type="button" onClick={onCancel} disabled={isSaving}>Cancel</button>}
      </div>
    </form>
  )
}

function LessonExercises({ lessonId }: { lessonId: string }) {
  const queryClient = useQueryClient()
  const coursesQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses })
  const lessonQuery = useQuery({ queryKey: ['teaching', 'lesson', lessonId], queryFn: () => getLesson(lessonId) })
  const course = coursesQuery.data?.find((item) => item.id === lessonQuery.data?.course_id)
  const exercisesQuery = useQuery({
    queryKey: exerciseQueryKey(lessonId),
    queryFn: () => listExercises(lessonId),
    enabled: Boolean(course && lessonQuery.data),
  })
  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const refreshExercises = async () => queryClient.invalidateQueries({ queryKey: exerciseQueryKey(lessonId) })
  const createMutation = useMutation({
    mutationFn: (value: ExerciseInput) => createExercise(lessonId, value),
    onSuccess: async () => { setCreating(false); await refreshExercises() },
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: Partial<ExerciseInput> }) => updateExercise(id, updates),
    onSuccess: async () => { setEditingId(null); await refreshExercises() },
  })
  const deleteMutation = useMutation({ mutationFn: deleteExercise, onSuccess: refreshExercises })

  if (coursesQuery.isPending || lessonQuery.isPending) return <div className="page-state" role="status">Loading lesson…</div>
  if (coursesQuery.error || lessonQuery.error) {
    const error = coursesQuery.error ?? lessonQuery.error
    return <div className="page-state page-state--error" role="alert"><h2>Lesson unavailable</h2><p>{learningError(error)}</p></div>
  }
  if (!lessonQuery.data || !course) return <div className="page-state page-state--error" role="alert"><h2>Lesson unavailable</h2><p>You do not have teaching access to this lesson.</p></div>

  const isSaving = createMutation.isPending || updateMutation.isPending
  async function saveExercise(value: ExerciseInput, exerciseId?: string) {
    setActionError(null)
    try {
      if (exerciseId) await updateMutation.mutateAsync({ id: exerciseId, updates: value })
      else await createMutation.mutateAsync(value)
    } catch (error) {
      setActionError(learningError(error))
      throw error
    }
  }

  async function togglePublished(exercise: Exercise) {
    const nextState = !exercise.is_published
    const prompt = nextState ? 'Publish this exercise for students?' : 'Unpublish this exercise? Students will no longer see it.'
    if (!window.confirm(prompt)) return
    setActionError(null)
    try {
      await updateMutation.mutateAsync({ id: exercise.id, updates: { is_published: nextState } })
    } catch (error) {
      setActionError(learningError(error))
    }
  }

  async function removeExercise(exercise: Exercise) {
    if (!window.confirm(`Delete “${exercise.title}”? This cannot be undone.`)) return
    setActionError(null)
    try {
      await deleteMutation.mutateAsync(exercise.id)
    } catch (error) {
      setActionError(learningError(error))
    }
  }

  return (
    <div className="page-stack">
      <Link className="teaching-back" to={`/teaching/courses/${course.id}`}><ArrowLeft size={17} aria-hidden="true" /> {course.name}</Link>
      <section className="page-heading-row teaching-heading">
        <div><span className="eyebrow">LESSON EXERCISES</span><h1>{lessonQuery.data.title}</h1><p>Create practice work and control student visibility.</p></div>
        {!creating && <button className="button button--primary" type="button" aria-label="New exercise" onClick={() => { setActionError(null); setCreating(true) }}><Plus size={18} aria-hidden="true" /><span className="teaching-button-label">New exercise</span></button>}
      </section>
      {actionError && <div className="form-alert" role="alert"><CircleAlert size={18} aria-hidden="true" />{actionError}</div>}
      {creating && <section className="teaching-editor" aria-labelledby="exercise-create-title"><h2 id="exercise-create-title">New exercise</h2><ExerciseForm isSaving={isSaving} onCancel={() => setCreating(false)} onSave={(value) => saveExercise(value)} /></section>}
      {exercisesQuery.isPending ? (
        <div className="page-state" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Loading exercises…</div>
      ) : exercisesQuery.error ? (
        <div className="page-state page-state--error" role="alert"><h2>Exercises unavailable</h2><p>{learningError(exercisesQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void exercisesQuery.refetch()}>Try again</button></div>
      ) : exercisesQuery.data.length === 0 && !creating ? (
        <section className="teaching-empty" aria-labelledby="exercise-empty-title"><ClipboardList size={27} aria-hidden="true" /><h2 id="exercise-empty-title">No exercises yet</h2><p>Start with a draft, then publish it when students are ready.</p><button className="button button--primary" type="button" onClick={() => setCreating(true)}><Plus size={18} aria-hidden="true" /> Create first exercise</button></section>
      ) : (
        <div className="lesson-list" aria-label="Lesson exercises">
          {exercisesQuery.data.map((exercise) => (
            <article className="lesson-row" key={exercise.id}>
              {editingId === exercise.id ? (
                <div className="lesson-row__editor"><h2>Edit exercise</h2><ExerciseForm exercise={exercise} isSaving={isSaving} onCancel={() => setEditingId(null)} onSave={(value) => saveExercise(value, exercise.id)} /></div>
              ) : (
                <>
                  <div className="lesson-row__main"><span className={`lesson-badge ${exercise.is_published ? 'lesson-badge--published' : ''}`}>{exercise.is_published ? 'Published' : 'Draft'}</span><h2>{exercise.title}</h2><p>{exercise.exercise_type} · Order {exercise.position}</p></div>
                  <div className="teaching-actions lesson-row__actions">
                    <button className="button button--outline" type="button" disabled={updateMutation.isPending} onClick={() => { setActionError(null); setEditingId(exercise.id) }}>Edit</button>
                    <button className="button button--outline" type="button" disabled={updateMutation.isPending} onClick={() => void togglePublished(exercise)}>{exercise.is_published ? 'Unpublish' : 'Publish'}</button>
                    <button className="icon-button icon-button--danger" type="button" aria-label={`Delete ${exercise.title}`} disabled={deleteMutation.isPending} onClick={() => void removeExercise(exercise)}><Trash2 size={18} aria-hidden="true" /></button>
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

export function ReviewForm({
  submission,
  isSaving,
  saved,
  saveError,
  onSave,
}: {
  submission: ExerciseSubmissionInboxItem
  isSaving: boolean
  saved: boolean
  saveError: string | null
  onSave: (feedback: string | null) => Promise<void>
}) {
  const [feedback, setFeedback] = useState(submission.feedback ?? '')
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      await onSave(feedback.trim() || null)
    } catch {
      setError('Your review could not be saved. Please try again.')
    }
  }

  return (
    <form className="teaching-form review-form" onSubmit={(event) => void submit(event)}>
      <div className="field">
        <label htmlFor="submission-feedback">Feedback</label>
        <textarea id="submission-feedback" value={feedback} onChange={(event) => setFeedback(event.target.value)} maxLength={20000} rows={6} />
        <span className="teaching-form__limit">{feedback.length}/20,000</span>
      </div>
      {(error || saveError) && <p className="inline-error" role="alert">{error ?? saveError}</p>}
      {saved && <p className="form-success" role="status">Review saved.</p>}
      <button className="button button--primary" type="submit" disabled={isSaving}>
        {isSaving ? <LoaderCircle className="spin" size={17} aria-hidden="true" /> : <Save size={17} aria-hidden="true" />}
        {isSaving ? 'Saving…' : 'Save review'}
      </button>
    </form>
  )
}

function ReviewInbox({ courseId }: { courseId: string }) {
  const coursesQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses })
  const course = coursesQuery.data?.find((item) => item.id === courseId)
  const submissionsQuery = useQuery({
    queryKey: ['teaching', 'course-submissions', courseId],
    queryFn: () => listCourseExerciseSubmissions(courseId),
    enabled: Boolean(course),
  })
  const [filter, setFilter] = useState<ReviewFilter>('NEEDS_REVIEW')

  if (coursesQuery.isPending) return <div className="page-state" role="status">Loading course…</div>
  if (coursesQuery.error) return <div className="page-state page-state--error" role="alert"><h2>Course unavailable</h2><p>{learningError(coursesQuery.error)}</p></div>
  if (!course) return <div className="page-state page-state--error" role="alert"><h2>Course unavailable</h2><p>You do not have teaching access to this course.</p></div>

  const submissions = submissionsQuery.data ?? []
  const visibleSubmissions = filterReviewSubmissions(submissions, filter)
  return (
    <div className="page-stack">
      <Link className="teaching-back" to={`/teaching/courses/${course.id}`}><ArrowLeft size={17} aria-hidden="true" /> {course.name}</Link>
      <section className="page-heading-row teaching-heading">
        <div><span className="eyebrow">{course.code}</span><h1>Review inbox</h1><p>Exercise submissions from your course.</p></div>
      </section>
      <div className="review-filters" role="group" aria-label="Filter submissions by review status">
        {([
          ['NEEDS_REVIEW', 'Needs review'],
          ['REVIEWED', 'Reviewed'],
          ['ALL', 'All submissions'],
        ] as const).map(([value, label]) => (
          <button className={`review-filter ${filter === value ? 'is-active' : ''}`} type="button" aria-pressed={filter === value} key={value} onClick={() => setFilter(value)}>
            {label}{value === 'NEEDS_REVIEW' && <span>{submissions.filter((submission) => submission.reviewed_at === null).length}</span>}
          </button>
        ))}
      </div>
      {submissionsQuery.isPending ? (
        <div className="page-state" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Loading submissions…</div>
      ) : submissionsQuery.error ? (
        <div className="page-state page-state--error" role="alert"><h2>Submissions unavailable</h2><p>{learningError(submissionsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void submissionsQuery.refetch()}>Try again</button></div>
      ) : visibleSubmissions.length === 0 ? (
        <section className="teaching-empty" aria-labelledby="review-empty-title"><ClipboardList size={27} aria-hidden="true" /><h2 id="review-empty-title">{filter === 'NEEDS_REVIEW' ? 'Nothing waiting for review' : 'No submissions here'}</h2><p>{filter === 'NEEDS_REVIEW' ? 'New student attempts will appear here.' : 'There are no submissions in this view.'}</p></section>
      ) : (
        <div className="review-list" aria-label="Course submissions">
          {visibleSubmissions.map((submission) => (
            <Link className="review-row" key={submission.id} to={`/teaching/courses/${course.id}/submissions/${submission.id}`}>
              <span className={`lesson-badge ${submission.reviewed_at ? 'lesson-badge--published' : ''}`}>{submission.reviewed_at ? 'Reviewed' : 'Needs review'}</span>
              <span className="review-row__student"><UserRound size={17} aria-hidden="true" /><strong>{submission.student_name}</strong></span>
              <span className="review-row__exercise"><strong>{submission.exercise_title}</strong><small>{submission.lesson_title}</small></span>
              <span className="review-row__time"><span>Attempt {submission.attempt_number}</span><time dateTime={submission.submitted_at}><Clock3 size={14} aria-hidden="true" />{new Date(submission.submitted_at).toLocaleString()}</time></span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

function SubmissionReview({ courseId, submissionId }: { courseId: string; submissionId: string }) {
  const queryClient = useQueryClient()
  const coursesQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses })
  const submissionsQuery = useQuery({
    queryKey: ['teaching', 'course-submissions', courseId],
    queryFn: () => listCourseExerciseSubmissions(courseId),
  })
  const course = coursesQuery.data?.find((item) => item.id === courseId)
  const submission = submissionsQuery.data?.find((item) => item.id === submissionId)
  const reviewMutation = useMutation({
    mutationFn: (feedback: string | null) => reviewExerciseSubmission(submissionId, feedback),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['teaching', 'course-submissions', courseId] }),
        queryClient.invalidateQueries({ queryKey: ['teaching', 'pending-reviews', courseId] }),
      ])
    },
  })

  if (coursesQuery.isPending || submissionsQuery.isPending) return <div className="page-state" role="status">Loading submission…</div>
  if (coursesQuery.error || submissionsQuery.error) {
    const error = coursesQuery.error ?? submissionsQuery.error
    return <div className="page-state page-state--error" role="alert"><h2>Submission unavailable</h2><p>{learningError(error)}</p></div>
  }
  if (!course || !submission) return <div className="page-state page-state--error" role="alert"><h2>Submission unavailable</h2><p>This submission may have been removed, or you may not teach this course.</p></div>

  const previousAttempts = (submissionsQuery.data ?? [])
    .filter((item) => item.exercise_id === submission.exercise_id && item.student_id === submission.student_id)
    .sort((left, right) => left.attempt_number - right.attempt_number)

  return (
    <div className="page-stack">
      <Link className="teaching-back" to={`/teaching/courses/${course.id}/reviews`}><ArrowLeft size={17} aria-hidden="true" /> Review inbox</Link>
      <section className="page-heading-row teaching-heading"><div><span className="eyebrow">{submission.lesson_title} · {submission.exercise_title}</span><h1>{submission.student_name}</h1><p>Attempt {submission.attempt_number} · Submitted <time dateTime={submission.submitted_at}>{new Date(submission.submitted_at).toLocaleString()}</time></p></div><span className={`lesson-badge ${submission.reviewed_at ? 'lesson-badge--published' : ''}`}>{submission.reviewed_at ? 'Reviewed' : 'Needs review'}</span></section>
      <section className="submission-answer" aria-labelledby="submission-answer-title"><h2 id="submission-answer-title">Student answer</h2><p>{submission.answer_text}</p></section>
      <section className="submission-history" aria-labelledby="submission-history-title"><h2 id="submission-history-title">Previous attempts</h2>{previousAttempts.length < 2 ? <p className="submission-history__empty">No previous attempts.</p> : <ol>{previousAttempts.filter((item) => item.id !== submission.id).map((item) => <li key={item.id}><strong>Attempt {item.attempt_number}</strong><time dateTime={item.submitted_at}>{new Date(item.submitted_at).toLocaleString()}</time><p>{item.answer_text}</p>{item.feedback && <blockquote>{item.feedback}</blockquote>}</li>)}</ol>}</section>
      <section className="teaching-editor" aria-labelledby="review-form-title"><h2 id="review-form-title">Review this attempt</h2><ReviewForm key={submission.id} submission={submission} isSaving={reviewMutation.isPending} saved={reviewMutation.isSuccess} saveError={reviewMutation.error ? learningError(reviewMutation.error) : null} onSave={(feedback) => reviewMutation.mutateAsync(feedback).then(() => undefined)} /></section>
    </div>
  )
}

export function TeachingPage() {
  const { courseId, lessonId, submissionId } = useParams()
  const { pathname } = useLocation()
  const coursesQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses })
  if (courseId && submissionId) return <SubmissionReview courseId={courseId} submissionId={submissionId} />
  if (courseId && pathname.endsWith('/reviews')) return <ReviewInbox courseId={courseId} />
  if (lessonId) return <LessonExercises lessonId={lessonId} />
  if (courseId) return <CourseLessons courseId={courseId} />
  return <TeachingHome courses={coursesQuery.data ?? []} isLoading={coursesQuery.isPending} error={coursesQuery.error} />
}