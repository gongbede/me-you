import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getTeachingCourses, listAdministeredInstitutions } from '../api/education'
import { listConversations } from '../api/messaging'
import { getMyProfile } from '../api/profile'
import { getUnreadNotificationCount } from '../api/notifications'
import { getPlatformAdminAccess } from '../api/moderation'
import { ThemeProvider } from '../hooks/useTheme'
import { AppShell } from './AppShell'

vi.mock('../api/education', () => ({ getTeachingCourses: vi.fn(), listAdministeredInstitutions: vi.fn() }))
vi.mock('../api/messaging', () => ({ listConversations: vi.fn() }))
vi.mock('../api/profile', () => ({ getMyProfile: vi.fn() }))
vi.mock('../api/notifications', () => ({ getUnreadNotificationCount: vi.fn() }))
vi.mock('../api/moderation', () => ({ getPlatformAdminAccess: vi.fn() }))
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'teacher-id', username: 'teacher', email: 'teacher@example.test' } }),
}))

const getCourses = vi.mocked(getTeachingCourses)
const getAdminInstitutions = vi.mocked(listAdministeredInstitutions)
const getConversations = vi.mocked(listConversations)
const getProfile = vi.mocked(getMyProfile)
const getUnreadNotifications = vi.mocked(getUnreadNotificationCount)
const getPlatformAccess = vi.mocked(getPlatformAdminAccess)

function renderAppShell(initialEntry = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <AppShell />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  )
}

describe('AppShell Teaching navigation', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    getCourses.mockReset()
    getAdminInstitutions.mockReset().mockResolvedValue([])
    getConversations.mockReset().mockResolvedValue([])
    getUnreadNotifications.mockReset().mockResolvedValue({ unread_count: 0 })
    getPlatformAccess.mockReset().mockResolvedValue({ is_platform_admin: false })
    getProfile.mockReset().mockResolvedValue({
      user_id: 'teacher-id',
      display_name: 'Teacher',
      bio: null,
      profile_picture_url: null,
      location: null,
      website: null,
      visibility: 'NETWORK',
      created_at: '',
      updated_at: '',
    })
  })

  it('shows the first-letter fallback when the user has no avatar', async () => {
    renderAppShell()

    const avatarButton = screen.getByRole('button', { name: 'Open profile menu' })
    expect(await within(avatarButton).findByText('T')).toBeInTheDocument()
    expect(within(avatarButton).queryByRole('img')).not.toBeInTheDocument()
  })

  it('shows the user avatar image when their profile has one', async () => {
    getProfile.mockResolvedValueOnce({
      user_id: 'teacher-id',
      display_name: 'Teacher',
      bio: null,
      profile_picture_url: 'https://example.test/teacher.png',
      location: null,
      website: null,
      visibility: 'NETWORK',
      created_at: '',
      updated_at: '',
    })
    renderAppShell()

    const avatarButton = screen.getByRole('button', { name: 'Open profile menu' })
    expect(await within(avatarButton).findByRole('img')).toHaveAttribute('src', 'https://example.test/teacher.png')
  })

  it('offers a retry when course lookup fails and restores Teaching on success', async () => {
    getCourses.mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce([{ id: 'course-1' }] as never)
    renderAppShell()

    const mainNavigation = screen.getByRole('navigation', { name: 'Main navigation' })
    fireEvent.click(within(mainNavigation).getByRole('button', { name: 'More navigation' }))
    const retry = await within(mainNavigation).findByRole('button', { name: 'Retry Teaching' })
    fireEvent.click(retry)

    expect(await within(mainNavigation).findByRole('link', { name: 'Teaching' })).toBeInTheDocument()
    expect(getCourses).toHaveBeenCalledTimes(2)
  })

  it('shows Administration only for users with an admin membership', async () => {
    getCourses.mockResolvedValue([])
    getAdminInstitutions.mockResolvedValue([{ id: 'school-1' }] as never)
    renderAppShell()

    const mainNavigation = screen.getByRole('navigation', { name: 'Main navigation' })
    fireEvent.click(within(mainNavigation).getByRole('button', { name: 'More navigation' }))
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

    const mainNavigation = screen.getByRole('navigation', { name: 'Main navigation' })
    fireEvent.click(within(mainNavigation).getByRole('button', { name: 'More navigation' }))
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

    const mainNavigation = screen.getByRole('navigation', { name: 'Main navigation' })
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

    const desktopNavigation = screen.getByRole('navigation', { name: 'Main navigation' })
    fireEvent.click(within(desktopNavigation).getByRole('button', { name: 'More navigation' }))
    expect(await within(desktopNavigation).findByRole('link', { name: 'Administration' })).toBeInTheDocument()
  })

  it('keeps active states on nested message and course classroom routes', async () => {
    getCourses.mockResolvedValue([])
    getAdminInstitutions.mockResolvedValue([])
    renderAppShell('/messages/conversation-1')

    const desktopNavigation = screen.getByRole('navigation', { name: 'Main navigation' })
    const mobileNavigation = screen.getByRole('navigation', { name: 'Mobile navigation' })
    expect(within(desktopNavigation).getByRole('link', { name: 'Messages' })).toHaveClass('is-active')
    expect(within(mobileNavigation).getByRole('link', { name: 'Messages' })).toHaveClass('is-active')

    cleanup()
    renderAppShell('/courses/course-1/classrooms')
    expect(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'My Courses' })).toHaveClass('is-active')
    expect(within(screen.getByRole('navigation', { name: 'Mobile navigation' })).getByRole('link', { name: 'My Courses' })).toHaveClass('is-active')
  })

  it('exposes desktop navigation and the five-item phone bar', async () => {
    getCourses.mockResolvedValue([])
    renderAppShell()

    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
    const phoneNavigation = screen.getByRole('navigation', { name: 'Mobile navigation' })
    expect(within(phoneNavigation).getAllByRole('link')).toHaveLength(4)
    expect(within(phoneNavigation).getByRole('button', { name: 'More' })).toBeInTheDocument()
  })

  it('expands the compact search control and focuses its input', async () => {
    getCourses.mockResolvedValue([])
    renderAppShell()

    const searchForm = screen.getByRole('search')
    const searchToggle = within(searchForm).getByRole('button', { name: 'Open search' })
    expect(searchForm).not.toHaveClass('is-expanded')
    expect(searchToggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(searchToggle)

    expect(searchForm).toHaveClass('is-expanded')
    const closeSearch = within(searchForm).getByRole('button', { name: 'Close search' })
    expect(closeSearch).toBeInTheDocument()
    await waitFor(() => expect(within(searchForm).getByRole('textbox', { name: 'Search' })).toHaveFocus())
    fireEvent.click(closeSearch)
    expect(searchForm).not.toHaveClass('is-expanded')
    expect(searchToggle).toHaveFocus()
  })

  it('closes desktop More on Escape and outside click', () => {
    getCourses.mockResolvedValue([])
    renderAppShell()
    const desktopNavigation = screen.getByRole('navigation', { name: 'Main navigation' })
    const trigger = within(desktopNavigation).getByRole('button', { name: 'More navigation' })

    fireEvent.click(trigger)
    expect(within(desktopNavigation).getByRole('navigation', { name: 'More navigation' })).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(within(desktopNavigation).queryByRole('navigation', { name: 'More navigation' })).not.toBeInTheDocument()

    fireEvent.click(trigger)
    fireEvent.mouseDown(document.body)
    expect(within(desktopNavigation).queryByRole('navigation', { name: 'More navigation' })).not.toBeInTheDocument()
  })

  it('shows platform Reports only for platform administrators', async () => {
    getCourses.mockResolvedValue([])
    getPlatformAccess.mockResolvedValue({ is_platform_admin: true })
    renderAppShell()

    const desktopNavigation = screen.getByRole('navigation', { name: 'Main navigation' })
    fireEvent.click(within(desktopNavigation).getByRole('button', { name: 'More navigation' }))
    expect(await within(desktopNavigation).findByRole('link', { name: 'Reports' })).toBeInTheDocument()
  })
})