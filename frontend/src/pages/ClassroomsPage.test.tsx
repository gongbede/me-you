import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { apiRequest } from '../api/client'
import { ClassroomScheduleForm, ClassroomsPage } from './ClassroomsPage'

vi.mock('../api/client', () => ({
  apiRequest: vi.fn(),
  ApiError: class ApiError extends Error { status = 500 },
  getFriendlyErrorMessage: (error: Error) => error.message,
}))

const request = vi.mocked(apiRequest)
const session = {
  id: 'session-1', course_id: 'course-1', created_by_id: 'teacher-1', title: 'Study circle',
  description: 'Practice together', starts_at: '2026-10-10T14:00:00Z', ends_at: '2026-10-10T15:00:00Z',
  status: 'LIVE', started_at: '2026-10-10T14:00:00Z', ended_at: null,
  created_at: '2026-10-10T12:00:00Z', updated_at: '2026-10-10T14:00:00Z',
} as const

function renderClassroom(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/courses/:courseId/classrooms/:sessionId" element={<ClassroomsPage />} />
          <Route path="/teaching/courses/:courseId/classrooms/:sessionId" element={<ClassroomsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Classrooms', () => {
  afterEach(() => cleanup())
  beforeEach(() => request.mockReset())

  it('rejects an end time that is not after the start time', async () => {
    const save = vi.fn()
    render(<ClassroomScheduleForm isSaving={false} onCancel={() => undefined} onSave={save} />)
    fireEvent.change(screen.getByLabelText('Class title'), { target: { value: 'Study circle' } })
    fireEvent.change(screen.getByLabelText('Starts'), { target: { value: '2026-10-10T14:00' } })
    fireEvent.change(screen.getByLabelText('Ends'), { target: { value: '2026-10-10T13:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Schedule classroom' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('end time after the start time')
    expect(save).not.toHaveBeenCalled()
  })

  it('requires a student to join a live classroom before sending chat', async () => {
    request.mockImplementation(async (path, options) => {
      if (path === '/api/v1/education/courses/course-1/class-sessions?limit=100') return [session] as never
      if (path === '/api/v1/education/class-sessions/session-1/messages?limit=100') return [] as never
      if (path === '/api/v1/education/class-sessions/session-1/join') return { session_id: 'session-1', user_id: 'student-1', status: 'PRESENT', joined_at: '2026-10-10T14:05:00Z' } as never
      if (path === '/api/v1/education/class-sessions/session-1/messages' && options?.method === 'POST') return {
        id: 'message-1', session_id: 'session-1', sender_id: 'student-1', sender_name: 'Student', message_type: 'CHAT', content: 'Hello class', created_at: '2026-10-10T14:06:00Z',
      } as never
      return undefined as never
    })
    renderClassroom('/courses/course-1/classrooms/session-1')
    expect(await screen.findByRole('button', { name: 'Join classroom' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Message')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Join classroom' }))
    expect(await screen.findByLabelText('Message')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Hello class' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    await waitFor(() => expect(request).toHaveBeenCalledWith('/api/v1/education/class-sessions/session-1/messages', expect.objectContaining({
      method: 'POST',
      body: { content: 'Hello class', message_type: 'CHAT' },
    })))
  })
})
