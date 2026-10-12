import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import {
  assignTeacherToCourse,
  createFaculty,
  deleteFaculty,
  getInstitutionCatalog,
  listCourseTeacherAssignments,
  listInstitutionTeachers,
} from '../api/education'
import { StructurePanel, TeachersPanel } from './AdminStructurePanels'

vi.mock('../api/education', () => ({
  assignTeacherToCourse: vi.fn(),
  createCourse: vi.fn(),
  createDepartment: vi.fn(),
  createFaculty: vi.fn(),
  deleteCourse: vi.fn(),
  deleteDepartment: vi.fn(),
  deleteFaculty: vi.fn(),
  getInstitutionCatalog: vi.fn(),
  listCourseTeacherAssignments: vi.fn(),
  listInstitutionTeachers: vi.fn(),
  removeTeacherFromCourse: vi.fn(),
  updateCourse: vi.fn(),
  updateDepartment: vi.fn(),
  updateFaculty: vi.fn(),
}))

const catalog = {
  institution: {
    id: 'school-1', name: 'Northside', description: null, public_description: null,
    is_listed: false, institution_type: 'SCHOOL' as const, website: null, location: null,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  },
  faculties: [],
}

function renderPanel(panel: 'structure' | 'teachers') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const component = panel === 'structure' ? <StructurePanel institutionId="school-1" /> : <TeachersPanel institutionId="school-1" />
  return render(<QueryClientProvider client={queryClient}>{component}</QueryClientProvider>)
}

describe('Administration structure and teachers', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    vi.mocked(getInstitutionCatalog).mockResolvedValue(catalog)
    vi.mocked(createFaculty).mockResolvedValue({ id: 'faculty-1', institution_id: 'school-1', name: 'Science', description: null, created_at: '', updated_at: '' })
    vi.mocked(deleteFaculty).mockResolvedValue()
    vi.mocked(listInstitutionTeachers).mockResolvedValue([])
    vi.mocked(listCourseTeacherAssignments).mockResolvedValue([])
    vi.mocked(assignTeacherToCourse).mockResolvedValue({ id: 'assignment-1', course_id: 'course-1', teacher_id: 'teacher-1', created_at: '', updated_at: '' })
  })

  it('creates a faculty through the real institution structure endpoint', async () => {
    renderPanel('structure')
    fireEvent.change(await screen.findByLabelText('Faculty name'), { target: { value: 'Science' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(vi.mocked(createFaculty)).toHaveBeenCalledWith('school-1', { name: 'Science', description: null }))
  })

  it('shows the real dependent-record conflict when deleting is blocked', async () => {
    const faculty = { id: 'faculty-1', institution_id: 'school-1', name: 'Science', description: null, created_at: '', updated_at: '' }
    vi.mocked(getInstitutionCatalog).mockResolvedValueOnce({ ...catalog, faculties: [{ faculty, departments: [] }] })
    vi.mocked(deleteFaculty).mockRejectedValueOnce(new ApiError('Faculty still has department records', 409))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPanel('structure')
    fireEvent.click(await screen.findByRole('button', { name: 'Delete faculty Science' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Faculty still has department records')
    expect(screen.getByRole('alert')).toHaveTextContent('Remove the dependent records first')
  })

  it('explains how a teacher record becomes available for assignment', async () => {
    renderPanel('teachers')

    expect(await screen.findByText(/must first request TEACHER membership/i)).toBeInTheDocument()
    expect(screen.getByText(/administrator must approve that request/i)).toBeInTheDocument()
  })

  it('assigns only an existing teacher record to a course', async () => {
    vi.mocked(listInstitutionTeachers).mockResolvedValueOnce([
      { id: 'teacher-1', user_id: 'teacher-user', institution_id: 'school-1', created_at: '', updated_at: '' },
    ])
    const course = { id: 'course-1', department_id: 'department-1', code: 'BIO-101', name: 'Biology', description: null, created_at: '', updated_at: '' }
    vi.mocked(getInstitutionCatalog).mockResolvedValueOnce({
      ...catalog,
      faculties: [{ faculty: { id: 'faculty-1', institution_id: 'school-1', name: 'Science', description: null, created_at: '', updated_at: '' }, departments: [{ department: { id: 'department-1', faculty_id: 'faculty-1', name: 'Biology', description: null, created_at: '', updated_at: '' }, courses: [course] }] }],
    })
    renderPanel('teachers')
    fireEvent.change(await screen.findByLabelText('Teacher for Biology'), { target: { value: 'teacher-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))

    await waitFor(() => expect(vi.mocked(assignTeacherToCourse)).toHaveBeenCalledWith('course-1', 'teacher-1'))
  })
})