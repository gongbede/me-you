import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import {
  approveInstitutionJoinRequest,
  getInstitution,
  listAdministeredInstitutions,
  listInstitutionJoinRequests,
  listInstitutionMembers,
  listSentInstitutionInvitations,
  updateInstitutionMemberRole,
} from '../api/education'
import { AdministrationPage } from './AdministrationPage'

vi.mock('../api/education', () => ({
  approveInstitutionJoinRequest: vi.fn(),
  cancelSentInstitutionInvitation: vi.fn(),
  getInstitution: vi.fn(),
  inviteInstitutionByEmail: vi.fn(),
  listAdministeredInstitutions: vi.fn(),
  listInstitutionJoinRequests: vi.fn(),
  listInstitutionMembers: vi.fn(),
  listSentInstitutionInvitations: vi.fn(),
  rejectInstitutionJoinRequest: vi.fn(),
  removeInstitutionMember: vi.fn(),
  updateInstitution: vi.fn(),
  updateInstitutionMemberRole: vi.fn(),
}))

const school = {
  id: 'school-1',
  name: 'Northside School',
  description: null,
  public_description: null,
  is_listed: false,
  institution_type: 'SCHOOL' as const,
  website: null,
  location: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const member = {
  id: 'membership-1',
  user_id: 'member-1',
  institution_id: school.id,
  role: 'ADMIN' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const request = {
  id: 'request-1',
  institution_id: school.id,
  user_id: 'student-1',
  role: 'STUDENT',
  request_type: 'JOIN',
  status: 'REQUESTED',
  created_by_user_id: 'student-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function renderAdministration(path = '/administration/schools/school-1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/administration" element={<AdministrationPage />} />
          <Route path="/administration/schools/:institutionId" element={<AdministrationPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AdministrationPage', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    vi.mocked(listAdministeredInstitutions).mockResolvedValue([school])
    vi.mocked(getInstitution).mockResolvedValue(school)
    vi.mocked(listInstitutionMembers).mockResolvedValue([member])
    vi.mocked(listInstitutionJoinRequests).mockResolvedValue([request])
    vi.mocked(listSentInstitutionInvitations).mockResolvedValue([])
    vi.mocked(approveInstitutionJoinRequest).mockResolvedValue({ ...member, user_id: request.user_id, role: request.role as 'STUDENT' })
    vi.mocked(updateInstitutionMemberRole).mockResolvedValue({ ...member, role: 'TEACHER' })
  })

  it('approves a pending join request with the real request id', async () => {
    renderAdministration()
    fireEvent.click(await screen.findByRole('tab', { name: 'Requests' }))
    fireEvent.click(await screen.findByRole('button', { name: /approve/i }))

    await waitFor(() => expect(vi.mocked(approveInstitutionJoinRequest)).toHaveBeenCalledWith('school-1', 'request-1'))
  })

  it('explains the final-admin role change protection in friendly words', async () => {
    vi.mocked(updateInstitutionMemberRole).mockRejectedValueOnce(
      new ApiError('Final administrator cannot be demoted', 409),
    )
    renderAdministration()
    fireEvent.change(await screen.findByLabelText('Role for member-1'), { target: { value: 'TEACHER' } })

    expect(await screen.findByRole('alert')).toHaveTextContent(/last active administrator/i)
    expect(screen.getByRole('alert')).toHaveTextContent(/add another administrator/i)
  })

  it('shows an empty state when the user administers no schools', async () => {
    vi.mocked(listAdministeredInstitutions).mockResolvedValueOnce([])
    renderAdministration('/administration')

    expect(await screen.findByText('No schools to administer')).toBeInTheDocument()
  })
})