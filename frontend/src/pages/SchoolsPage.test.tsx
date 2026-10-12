import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  listInstitutions,
  listMyInvitations,
  listMyStudents,
  listMyTeachers,
  requestStudentMembership,
  createInstitution,
  searchListedInstitutions,
} from '../api/education'
import { SchoolsPage } from './SchoolsPage'

vi.mock('../api/education', () => ({
  acceptInvitation: vi.fn(),
  createInstitution: vi.fn(),
  declineInvitation: vi.fn(),
  listInstitutions: vi.fn(),
  listMyInvitations: vi.fn(),
  listMyStudents: vi.fn(),
  listMyTeachers: vi.fn(),
  requestStudentMembership: vi.fn(),
  searchListedInstitutions: vi.fn(),
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

const listedSchool = {
  id: 'school-1',
  name: 'Northside School',
  institution_type: 'SCHOOL' as const,
  description: 'A public school description',
}

function renderSchools() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><SchoolsPage /></MemoryRouter></QueryClientProvider>)
}

describe('SchoolsPage', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    vi.mocked(listInstitutions).mockResolvedValue([])
    vi.mocked(listMyInvitations).mockResolvedValue([])
    vi.mocked(listMyStudents).mockResolvedValue([])
    vi.mocked(listMyTeachers).mockResolvedValue([])
    vi.mocked(searchListedInstitutions).mockResolvedValue([])
    vi.mocked(requestStudentMembership).mockResolvedValue(pendingRequest)
    vi.mocked(createInstitution).mockResolvedValue({
      id: 'new-school',
      name: 'New School',
      description: null,
      public_description: null,
      is_listed: false,
      institution_type: 'SCHOOL',
      website: null,
      location: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })
  })

  it('submits a real student membership request and shows its pending status', async () => {
    renderSchools()
    fireEvent.change(screen.getByLabelText('School ID'), { target: { value: 'school-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Request with ID' }))

    expect(await screen.findByRole('status')).toHaveTextContent('requested')
    expect(vi.mocked(requestStudentMembership).mock.calls[0]?.[0]).toBe('school-1')
  })

  it('searches the listed directory and shows the real pending request status', async () => {
    vi.mocked(searchListedInstitutions).mockResolvedValueOnce([listedSchool])
    renderSchools()
    fireEvent.change(screen.getByLabelText('Search schools'), { target: { value: 'Northside' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    fireEvent.click(await screen.findByRole('button', { name: 'Request to join' }))
    expect((await screen.findAllByText('Request requested')).length).toBeGreaterThan(0)
    expect(vi.mocked(searchListedInstitutions)).toHaveBeenCalledWith('Northside')
    expect(vi.mocked(requestStudentMembership).mock.calls[0]?.[0]).toBe('school-1')
  })

  it('creates a school with opt-in listing and confirms the caller is its administrator', async () => {
    renderSchools()
    fireEvent.change(screen.getByLabelText('School name'), { target: { value: 'Northside School' } })
    fireEvent.change(screen.getByLabelText('Public description (optional, up to 500 characters)'), { target: { value: 'Open to everyone' } })
    fireEvent.click(screen.getByLabelText('List this school in Find a school'))
    fireEvent.click(screen.getByRole('button', { name: 'Create school' }))

    expect(await screen.findByText(/you are its administrator/i)).toBeInTheDocument()
    expect(vi.mocked(createInstitution)).toHaveBeenCalledWith({
      name: 'Northside School',
      institution_type: 'SCHOOL',
      public_description: 'Open to everyone',
      is_listed: true,
    })
  })

  it('shows an empty state when the student has no active schools', async () => {
    renderSchools()

    expect(await screen.findByText(/find a listed school, accept an invitation, or create a school/i)).toBeInTheDocument()
  })

  it('shows a retryable error when school memberships fail to load', async () => {
    vi.mocked(listInstitutions).mockRejectedValueOnce(new Error('School service unavailable'))
    renderSchools()

    expect(await screen.findByRole('alert')).toHaveTextContent('School service unavailable')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('shows a retry action when directory search fails', async () => {
    vi.mocked(searchListedInstitutions).mockRejectedValueOnce(new Error('Directory unavailable'))
    renderSchools()
    fireEvent.change(screen.getByLabelText('Search schools'), { target: { value: 'Northside' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Directory unavailable')
    expect(screen.getByRole('button', { name: 'Retry search' })).toBeInTheDocument()
  })

  it('keeps school creation controls labeled and operable by keyboard at 390px', async () => {
    const user = userEvent.setup()
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    renderSchools()
    const nameInput = screen.getByLabelText('School name')
    await user.click(nameInput)
    await user.keyboard('Westside School{Enter}')

    expect(screen.getByLabelText('Type')).toBeInTheDocument()
    expect(screen.getByLabelText('List this school in Find a school')).toBeInTheDocument()
    expect(vi.mocked(createInstitution)).toHaveBeenCalledWith(expect.objectContaining({ name: 'Westside School' }))
  })
})