import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getTeachingCourses, listAdministeredInstitutions } from '../api/education'
import { listConversations } from '../api/messaging'
import { AppShell } from './AppShell'

vi.mock('../api/education', () => ({ getTeachingCourses: vi.fn(), listAdministeredInstitutions: vi.fn() }))
vi.mock('../api/messaging', () => ({ listConversations: vi.fn() }))
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { username: 'teacher', email: 'teacher@example.test' } }),
}))

const getCourses = vi.mocked(getTeachingCourses)
const getAdminInstitutions = vi.mocked(listAdministeredInstitutions)
const getConversations = vi.mocked(listConversations)

function renderAppShell(initialEntry = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
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
    getConversations.mockReset().mockResolvedValue([])
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

  it('shows the API-provided unread count beside Messages', async () => {
    getCourses.mockResolvedValue([])
    getConversations.mockResolvedValue([{
      id: 'conversation-1', type: 'DIRECT', name: null, description: null,
      created_at: '', updated_at: '', members: [], last_message_preview: null,
      last_message_at: null, unread_count: 4,
    }])
    renderAppShell()

    const mainNavigation = screen.getByRole('complementary', { name: 'Main navigation' })
    expect(await within(mainNavigation).findByRole('link', { name: 'Messages, 4 unread' })).toBeInTheDocument()
  })

  it('keeps five mobile destinations and traps focus in the More sheet', async () => {
    getCourses.mockResolvedValue([{ id: 'course-1' }] as never)
    getAdminInstitutions.mockResolvedValue([])
    renderAppShell()

    const mobileNavigation = screen.getByRole('navigation', { name: 'Mobile navigation' })
    expect(within(mobileNavigation).getAllByRole('link')).toHaveLength(4)
    expect(within(mobileNavigation).getAllByRole('button')).toHaveLength(1)
    const trigger = within(mobileNavigation).getByRole('button', { name: 'More' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(trigger)

    const sheet = await screen.findByRole('dialog', { name: 'More' })
    const first = within(sheet).getByRole('link', { name: 'Profile' })
    const closeButton = within(sheet).getByRole('button', { name: 'Close More menu' })
    const last = within(sheet).getByRole('link', { name: 'Sign out' })
    expect(first).toHaveFocus()
    expect(await within(sheet).findByRole('link', { name: 'Teaching' })).toBeInTheDocument()
    expect(within(sheet).queryByRole('link', { name: 'Administration' })).not.toBeInTheDocument()

    closeButton.focus()
    fireEvent.keyDown(closeButton, { key: 'Tab', shiftKey: true })
    expect(last).toHaveFocus()
    last.focus()
    fireEvent.keyDown(last, { key: 'Tab' })
    expect(closeButton).toHaveFocus()
    fireEvent.keyDown(sheet, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'More' })).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('offers Administration in More only when the membership lookup allows it', async () => {
    getCourses.mockResolvedValue([])
    getAdminInstitutions.mockResolvedValue([{ id: 'school-1' }] as never)
    renderAppShell()

    fireEvent.click(screen.getByRole('button', { name: 'More' }))
    expect(await within(await screen.findByRole('dialog', { name: 'More' })).findByRole('link', { name: 'Administration' })).toBeInTheDocument()
  })

  it('keeps active states on nested message and course classroom routes', async () => {
    getCourses.mockResolvedValue([])
    getAdminInstitutions.mockResolvedValue([])
    renderAppShell('/messages/conversation-1')

    const sidebar = screen.getByRole('complementary', { name: 'Main navigation' })
    const mobileNavigation = screen.getByRole('navigation', { name: 'Mobile navigation' })
    expect(within(sidebar).getByRole('link', { name: 'Messages' })).toHaveClass('is-active')
    expect(within(mobileNavigation).getByRole('link', { name: 'Messages' })).toHaveClass('is-active')

    cleanup()
    renderAppShell('/courses/course-1/classrooms')
    expect(within(screen.getByRole('complementary', { name: 'Main navigation' })).getByRole('link', { name: 'My Courses' })).toHaveClass('is-active')
    expect(within(screen.getByRole('navigation', { name: 'Mobile navigation' })).getByRole('link', { name: 'My Courses' })).toHaveClass('is-active')
  })
})