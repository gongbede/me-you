import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  listInstitutions,
  listMyInvitations,
  listMyStudents,
  listMyTeachers,
  requestStudentMembership,
  searchResources,
} from '../api/education'
import { SchoolsPage } from './SchoolsPage'

vi.mock('../api/education', () => ({
  acceptInvitation: vi.fn(),
  declineInvitation: vi.fn(),
  listInstitutions: vi.fn(),
  listMyInvitations: vi.fn(),
  listMyStudents: vi.fn(),
  listMyTeachers: vi.fn(),
  requestStudentMembership: vi.fn(),
  searchResources: vi.fn(),
}))

const pendingRequest = {
  id: 'request-1',
  institution_id: 'school-1',
  user_id: 'student-1',
  role: 'STUDENT',
  request_type: 'JOIN',
  status: 'REQUESTED',
  created_by_user_id: 'student-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function renderSchools() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><SchoolsPage /></MemoryRouter></QueryClientProvider>)
}

describe('SchoolsPage', () => {
  beforeEach(() => {
    vi.mocked(listInstitutions).mockResolvedValue([])
    vi.mocked(listMyInvitations).mockResolvedValue([])
    vi.mocked(listMyStudents).mockResolvedValue([])
    vi.mocked(listMyTeachers).mockResolvedValue([])
    vi.mocked(searchResources).mockResolvedValue({ query: '', items: [], offset: 0, limit: 100, has_more: false, next_cursor: null })
    vi.mocked(requestStudentMembership).mockResolvedValue(pendingRequest)
  })

  it('submits a real student membership request and shows its pending status', async () => {
    renderSchools()
    fireEvent.change(screen.getByLabelText('School ID'), { target: { value: 'school-1' } })
    fireEvent.click(screen.getByRole('button', { name: /request to join/i }))

    expect(await screen.findByRole('status')).toHaveTextContent('requested')
    expect(vi.mocked(requestStudentMembership).mock.calls[0]?.[0]).toBe('school-1')
  })

  it('shows an empty state when the student has no active schools', async () => {
    renderSchools()

    expect(await screen.findByText(/you do not have an active school membership yet/i)).toBeInTheDocument()
  })

  it('shows a retryable error when school memberships fail to load', async () => {
    vi.mocked(listInstitutions).mockRejectedValueOnce(new Error('School service unavailable'))
    renderSchools()

    expect(await screen.findByRole('alert')).toHaveTextContent('School service unavailable')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})