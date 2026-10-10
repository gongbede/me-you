import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from '../api/client'
import { ExerciseForm, LessonForm, ReviewForm, TeachingPage } from './TeachingPage'
import type { ExerciseSubmissionInboxItem } from '../api/education'
import { filterReviewSubmissions } from './teachingHelpers'

vi.mock('../api/client', () => ({
  apiRequest: vi.fn(),
  ApiError: class ApiError extends Error { status = 500 },
  getFriendlyErrorMessage: (error: Error) => error.message,
}))

const request = vi.mocked(apiRequest)
const course = { id: 'course-1', department_id: 'department-1', code: 'BIO101', name: 'Biology', description: null }
const teacher = { id: 'teacher-1', user_id: 'user-1', institution_id: 'school-1' }

function renderTeaching(path = '/teaching') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/teaching" element={<TeachingPage />} />
          <Route path="/teaching/courses/:courseId" element={<TeachingPage />} />
          <Route path="/teaching/lessons/:lessonId" element={<TeachingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Teaching area', () => {
  afterEach(() => cleanup())
  beforeEach(() => request.mockReset())

  it('rejects blank lesson title/content and negative order', async () => {
    const save = vi.fn()
    render(<LessonForm isSaving={false} onSave={save} />)
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Add a title and content')
    expect(save).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Topic' } })
    fireEvent.change(screen.getByLabelText('Content'), { target: { value: 'Details' } })
    fireEvent.change(screen.getByLabelText('Order'), { target: { value: '-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('order of 0 or greater')
    expect(save).not.toHaveBeenCalled()
  })

  it('confirms publish and sends the update only after confirmation', async () => {
    request.mockImplementation(async (path) => {
      if (path === '/api/v1/education/teachers/me?limit=100') return [teacher] as never
      if (path === '/api/v1/institutions/school-1') return { id: 'school-1', name: 'School' } as never
      if (path === '/api/v1/institutions/school-1/faculties?limit=100') return [{ id: 'faculty-1' }] as never
      if (path === '/api/v1/institutions/faculties/faculty-1/departments?limit=100') return [{ id: 'department-1' }] as never
      if (path === '/api/v1/institutions/departments/department-1/courses?limit=100') return [course] as never
      if (path === '/api/v1/education/courses/course-1/teachers?limit=100') return [{ teacher_id: 'teacher-1' }] as never
      if (path === '/api/v1/education/courses/course-1/lessons?limit=100') return [{ id: 'lesson-1', course_id: 'course-1', title: 'Cells', content: 'Cell basics', position: 0, is_published: false }] as never
      if (path === '/api/v1/education/lessons/lesson-1') return { id: 'lesson-1', course_id: 'course-1', title: 'Cells', content: 'Cell basics', position: 0, is_published: true } as never
      return undefined as never
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderTeaching('/teaching/courses/course-1')
    const publish = await screen.findByRole('button', { name: 'Publish' })
    fireEvent.click(publish)
    expect(confirm).toHaveBeenCalledWith('Publish this lesson for enrolled students?')
    expect(request).not.toHaveBeenCalledWith('/api/v1/education/lessons/lesson-1', expect.anything())
    confirm.mockReturnValue(true)
    fireEvent.click(publish)
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/v1/education/lessons/lesson-1', expect.objectContaining({ method: 'PATCH' })))
    confirm.mockRestore()
  })

  it('shows the empty teaching state when there are no course assignments', async () => {
    request.mockResolvedValueOnce([] as never)
    renderTeaching()
    expect(await screen.findByRole('heading', { name: 'No courses assigned yet' })).toBeInTheDocument()
  })

  it('validates exercise title, instructions, and order against the API limits', async () => {
    const save = vi.fn()
    render(<ExerciseForm isSaving={false} onSave={save} />)
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'x'.repeat(201) } })
    fireEvent.change(screen.getByLabelText('Instructions'), { target: { value: 'Instructions' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Add a title and instructions')
    expect(save).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Reflection' } })
    fireEvent.change(screen.getByLabelText('Order'), { target: { value: '-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('order of 0 or greater')
    expect(save).not.toHaveBeenCalled()
  })

  it('confirms exercise publication and persists the publish flag', async () => {
    request.mockImplementation(async (path) => {
      if (path === '/api/v1/education/teachers/me?limit=100') return [teacher] as never
      if (path === '/api/v1/institutions/school-1') return { id: 'school-1', name: 'School' } as never
      if (path === '/api/v1/institutions/school-1/faculties?limit=100') return [{ id: 'faculty-1' }] as never
      if (path === '/api/v1/institutions/faculties/faculty-1/departments?limit=100') return [{ id: 'department-1' }] as never
      if (path === '/api/v1/institutions/departments/department-1/courses?limit=100') return [course] as never
      if (path === '/api/v1/education/courses/course-1/teachers?limit=100') return [{ teacher_id: 'teacher-1' }] as never
      if (path === '/api/v1/education/lessons/lesson-1') return { id: 'lesson-1', course_id: 'course-1', title: 'Cells', content: 'Cell basics', position: 0, is_published: true } as never
      if (path === '/api/v1/education/lessons/lesson-1/exercises?limit=100') return [{ id: 'exercise-1', lesson_id: 'lesson-1', title: 'Explain', instructions: 'Explain cells', position: 0, exercise_type: 'WRITTEN', is_published: false }] as never
      if (path === '/api/v1/education/exercises/exercise-1') return { id: 'exercise-1', lesson_id: 'lesson-1', title: 'Explain', instructions: 'Explain cells', position: 0, exercise_type: 'WRITTEN', is_published: true } as never
      return undefined as never
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderTeaching('/teaching/lessons/lesson-1')
    fireEvent.click(await screen.findByRole('button', { name: 'Publish' }))
    expect(confirm).toHaveBeenCalledWith('Publish this exercise for students?')
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/v1/education/exercises/exercise-1', expect.objectContaining({
      method: 'PATCH',
      body: { is_published: true },
    })))
    confirm.mockRestore()
  })

  it('saves feedback without inventing a review status choice', async () => {
    const save = vi.fn().mockResolvedValue(undefined)
    const submission: ExerciseSubmissionInboxItem = {
      id: 'submission-1', exercise_id: 'exercise-1', student_id: 'student-1',
      attempt_number: 1, answer_text: 'My answer', feedback: null, reviewer_id: null,
      submitted_at: '2026-10-09T12:00:00Z', reviewed_at: null, created_at: '2026-10-09T12:00:00Z',
      updated_at: '2026-10-09T12:00:00Z', student_name: 'Student One', lesson_id: 'lesson-1',
      lesson_title: 'Cells', exercise_title: 'Explain',
    }
    render(<ReviewForm submission={submission} isSaving={false} saved={false} saveError={null} onSave={save} />)
    const feedback = screen.getByLabelText('Feedback')
    expect(feedback).toHaveAttribute('maxLength', '20000')
    fireEvent.change(feedback, { target: { value: 'Clear explanation.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save review' }))
    await waitFor(() => expect(save).toHaveBeenCalledWith('Clear explanation.'))
  })

  it('filters inbox rows using reviewed_at', () => {
    const base: ExerciseSubmissionInboxItem = {
      id: 'submission-1', exercise_id: 'exercise-1', student_id: 'student-1',
      attempt_number: 1, answer_text: 'My answer', feedback: null, reviewer_id: null,
      submitted_at: '2026-10-09T12:00:00Z', reviewed_at: null, created_at: '2026-10-09T12:00:00Z',
      updated_at: '2026-10-09T12:00:00Z', student_name: 'Student One', lesson_id: 'lesson-1',
      lesson_title: 'Cells', exercise_title: 'Explain',
    }
    const reviewed = { ...base, id: 'submission-2', reviewed_at: '2026-10-09T13:00:00Z' }
    expect(filterReviewSubmissions([base, reviewed], 'NEEDS_REVIEW')).toEqual([base])
    expect(filterReviewSubmissions([base, reviewed], 'REVIEWED')).toEqual([reviewed])
    expect(filterReviewSubmissions([base, reviewed], 'ALL')).toHaveLength(2)
  })
})