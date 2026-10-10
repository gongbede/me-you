import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpen, CircleAlert, ClipboardList, LoaderCircle, Plus, Save, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
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
  updateExercise,
  updateLesson,
  type Course,
  type Exercise,
  type ExerciseInput,
  type Lesson,
  type LessonInput,
} from '../api/education'

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
        {!creating && <button className="button button--primary" type="button" onClick={() => { setActionError(null); setCreating(true) }}><Plus size={18} aria-hidden="true" /> New lesson</button>}
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

export function TeachingPage() {
  const { courseId, lessonId } = useParams()
  const coursesQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses })
  if (lessonId) return <LessonExercises lessonId={lessonId} />
  if (courseId) return <CourseLessons courseId={courseId} />
  return <TeachingHome courses={coursesQuery.data ?? []} isLoading={coursesQuery.isPending} error={coursesQuery.error} />
}