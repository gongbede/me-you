import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getLesson, getLessonProgress, listExercises, setLessonProgress } from '../api/education'
import { LessonPage } from './LessonPage'

vi.mock('../api/education', () => ({
  getLesson: vi.fn(),
  getLessonProgress: vi.fn(),
  listExercises: vi.fn(),
  listExerciseSubmissions: vi.fn(),
  setLessonProgress: vi.fn(),
  submitExercise: vi.fn(),
}))

describe('LessonPage progress', () => {
  beforeEach(() => {
    vi.mocked(getLesson).mockResolvedValue({
      id: 'lesson-1',
      course_id: 'course-1',
      title: 'Getting started',
      content: 'Read this lesson.',
      position: 0,
      is_published: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })
    vi.mocked(getLessonProgress).mockResolvedValue(null)
    vi.mocked(listExercises).mockResolvedValue([])
  })

  it('rolls completion back after the progress update fails', async () => {
    let rejectUpdate: ((error: Error) => void) | undefined
    vi.mocked(setLessonProgress).mockImplementation(() => new Promise((_resolve, reject) => {
      rejectUpdate = reject
    }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/lessons/lesson-1']}>
          <Routes><Route path="/lessons/:lessonId" element={<LessonPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Mark as done' }))
    const savingButton = await screen.findByRole('button', { name: 'Saving…' })
    expect(savingButton).toHaveAttribute('aria-pressed', 'true')
    expect(savingButton).toBeDisabled()
    await act(async () => rejectUpdate?.(new Error('Progress service unavailable')))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Mark as done' })).toBeEnabled())
    expect(screen.getByRole('alert')).toHaveTextContent('Progress service unavailable')
    expect(setLessonProgress).toHaveBeenCalledWith('lesson-1', true)
  })
})