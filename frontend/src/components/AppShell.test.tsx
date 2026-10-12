import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getTeachingCourses, listAdministeredInstitutions } from '../api/education'
import { AppShell } from './AppShell'

vi.mock('../api/education', () => ({ getTeachingCourses: vi.fn(), listAdministeredInstitutions: vi.fn() }))
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { username: 'teacher', email: 'teacher@example.test' } }),
}))

const getCourses = vi.mocked(getTeachingCourses)
const getAdminInstitutions = vi.mocked(listAdministeredInstitutions)

function renderAppShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AppShell Teaching navigation', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    getCourses.mockReset()
    getAdminInstitutions.mockReset().mockResolvedValue([])
  })

  it('offers a retry when course lookup fails and restores Teaching on success', async () => {
    getCourses.mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce([{ id: 'course-1' }] as never)
    renderAppShell()

    const mainNavigation = screen.getByRole('complementary', { name: 'Main navigation' })
    const retry = await within(mainNavigation).findByRole('button', { name: 'Retry Teaching' })
    fireEvent.click(retry)

    expect(await within(mainNavigation).findByRole('link', { name: 'Teaching' })).toBeInTheDocument()
    expect(getCourses).toHaveBeenCalledTimes(2)
  })

  it('shows Administration only for users with an admin membership', async () => {
    getCourses.mockResolvedValue([])
    getAdminInstitutions.mockResolvedValue([{ id: 'school-1' }] as never)
    renderAppShell()

    const mainNavigation = screen.getByRole('complementary', { name: 'Main navigation' })
    expect(await within(mainNavigation).findByRole('link', { name: 'Administration' })).toBeInTheDocument()
  })

  it('hides Administration from non-admins', async () => {
    getCourses.mockResolvedValue([])
    getAdminInstitutions.mockResolvedValue([])
    renderAppShell()

    await waitFor(() => expect(getAdminInstitutions).toHaveBeenCalled())
    expect(screen.queryByRole('link', { name: 'Administration' })).not.toBeInTheDocument()
  })

  it('offers a retry when the administrator lookup fails', async () => {
    getCourses.mockResolvedValue([])
    getAdminInstitutions.mockRejectedValueOnce(new Error('Admin lookup unavailable')).mockResolvedValueOnce([{ id: 'school-1' }] as never)
    renderAppShell()

    const mainNavigation = screen.getByRole('complementary', { name: 'Main navigation' })
    fireEvent.click(await within(mainNavigation).findByRole('button', { name: 'Retry Administration' }))
    expect(await within(mainNavigation).findByRole('link', { name: 'Administration' })).toBeInTheDocument()
    expect(getAdminInstitutions).toHaveBeenCalledTimes(2)
  })
})