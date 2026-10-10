import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpen, CircleAlert, LoaderCircle, Plus, Save, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, getFriendlyErrorMessage } from '../api/client'
import {
  createLesson,
  deleteLesson,
  getCourseLessons,
  getTeachingCourses,
  updateLesson,
  type Course,
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
          {courses.map((course) => (
            <Link className="teaching-course" key={course.id} to={`/teaching/courses/${course.id}`}>
              <span className="teaching-course__icon"><BookOpen size={21} aria-hidden="true" /></span>
              <span className="teaching-course__copy"><strong>{course.name}</strong><small>{course.code}</small></span>
              <span className="teaching-course__unavailable">Student and review counts unavailable</span>
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

export function TeachingPage() {
  const { courseId } = useParams()
  const coursesQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses })
  if (courseId) return <CourseLessons courseId={courseId} />
  return <TeachingHome courses={coursesQuery.data ?? []} isLoading={coursesQuery.isPending} error={coursesQuery.error} />
}