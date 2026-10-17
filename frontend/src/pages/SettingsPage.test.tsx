import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getNotificationPreferences,
  updateNotificationPreferences,
} from '../api/notifications'
import { listBlockedUsers, unblockUser } from '../api/moderation'
import { SettingsPage } from './SettingsPage'
import { ThemeProvider } from '../hooks/useTheme'
import {
  changeMyPassword,
  deleteMyAccount,
  getMyAccount,
  requestEmailChange,
  requestEmailVerification,
  revokeAllSessions,
} from '../api/auth'
import { getMyProfile, updateMyProfile } from '../api/profile'

vi.mock('../api/auth', () => ({
  changeMyPassword: vi.fn(),
  deleteMyAccount: vi.fn(),
  getMyAccount: vi.fn(),
  requestEmailChange: vi.fn(),
  requestEmailVerification: vi.fn(),
  revokeAllSessions: vi.fn(),
  logout: vi.fn(),
}))
vi.mock('../api/profile', () => ({
  getMyProfile: vi.fn(),
  updateMyProfile: vi.fn(),
}))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => ({ logout: vi.fn() }) }))

vi.mock('../api/notifications', () => ({
  getNotificationPreferences: vi.fn(),
  updateNotificationPreferences: vi.fn(),
}))
vi.mock('../api/moderation', () => ({
  listBlockedUsers: vi.fn(),
  unblockUser: vi.fn(),
}))

const preferences = {
  COMMENT: true,
  FOLLOW: true,
  LIKE: true,
  MESSAGE: true,
  CLASS_ANNOUNCEMENT: true,
  EXERCISE_SUBMISSION: true,
  EXERCISE_REVIEWED: true,
}
const profile = {
  user_id: 'user-id',
  display_name: 'Learner',
  bio: null,
  profile_picture_url: null,
  location: null,
  website: null,
  visibility: 'PUBLIC' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<ThemeProvider><QueryClientProvider client={queryClient}><MemoryRouter><SettingsPage /></MemoryRouter></QueryClientProvider></ThemeProvider>)
}

describe('SettingsPage', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(getNotificationPreferences).mockResolvedValue({ preferences })
    vi.mocked(updateNotificationPreferences).mockResolvedValue({
      preferences: { ...preferences, FOLLOW: false },
    })
    vi.mocked(listBlockedUsers).mockResolvedValue([])
    vi.mocked(unblockUser).mockResolvedValue(undefined)
    vi.mocked(getMyAccount).mockResolvedValue({
      id: 'user-id', username: 'learner', email: 'learner@example.test',
      email_verified_at: null, created_at: '2026-01-01T00:00:00Z',
    })
    vi.mocked(getMyProfile).mockResolvedValue(profile)
    vi.mocked(updateMyProfile).mockResolvedValue({ ...profile, visibility: 'FOLLOWERS' })
    vi.mocked(changeMyPassword).mockResolvedValue({ message: 'Password updated' })
    vi.mocked(requestEmailChange).mockResolvedValue({ message: 'If the address is eligible, a confirmation message will be sent' })
    vi.mocked(requestEmailVerification).mockResolvedValue({ message: 'Verification sent' })
    vi.mocked(revokeAllSessions).mockResolvedValue({ message: 'All account sessions have been revoked' })
    vi.mocked(deleteMyAccount).mockResolvedValue({ message: 'Account deleted' })
  })

  it('lets the user choose a theme from Settings', async () => {
    renderPage()
    fireEvent.change(screen.getByRole('combobox', { name: 'Theme' }), { target: { value: 'dark' } })

    await waitFor(() => expect(document.documentElement).toHaveAttribute('data-theme', 'dark'))
    expect(localStorage.getItem('me-you-theme')).toBe('dark')
  })

  it('loads and saves notification preferences', async () => {
    renderPage()

    const followToggle = await screen.findByRole('checkbox', { name: 'Toggle new followers notifications' })
    expect(followToggle).toBeChecked()
    expect(screen.getByText(/Your email is not verified/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Resend verification email' }))
    await waitFor(() => expect(vi.mocked(requestEmailVerification).mock.calls).toHaveLength(1))
    fireEvent.click(followToggle)

    await waitFor(() => expect(vi.mocked(updateNotificationPreferences).mock.calls[0]?.[0]).toEqual({
      preferences: { FOLLOW: false },
    }))
    expect(await screen.findByText('Notification preferences saved.')).toBeInTheDocument()
    expect(followToggle).not.toBeChecked()
  })

  it('shows a loading state while preferences are being fetched', () => {
    vi.mocked(getNotificationPreferences).mockReturnValueOnce(new Promise(() => undefined))
    renderPage()

    expect(screen.getByText(/Loading notification preferences/)).toBeInTheDocument()
  })

  it('shows blocked users and supports unblocking', async () => {
    vi.mocked(listBlockedUsers).mockResolvedValue([{ id: 'blocked-id', username: 'blocked-person' }])
    renderPage()

    expect(await screen.findByText('@blocked-person')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Unblock' }))
    await waitFor(() => expect(vi.mocked(unblockUser).mock.calls[0]?.[0]).toBe('blocked-id'))
  })

  it('submits account security, privacy, email, and deletion settings', async () => {
    renderPage()

    const passwordSection = await screen.findByRole('heading', { name: 'Change password' })
    const passwordForm = passwordSection.closest('form')
    if (!passwordForm) throw new Error('Password form not found')
    fireEvent.change(within(passwordForm).getByLabelText('Current password'), { target: { value: 'old-password' } })
    fireEvent.change(within(passwordForm).getByLabelText('New password'), { target: { value: 'new-password' } })
    fireEvent.submit(passwordForm)
    await waitFor(() => expect(vi.mocked(changeMyPassword).mock.calls[0]?.[0]).toEqual({
      current_password: 'old-password', new_password: 'new-password',
    }))

    fireEvent.change(screen.getByLabelText('Profile visibility'), { target: { value: 'FOLLOWERS' } })
    await waitFor(() => expect(vi.mocked(updateMyProfile).mock.calls[0]?.[0]).toEqual({ visibility: 'FOLLOWERS' }))

    const emailForm = screen.getByRole('heading', { name: 'Change email' }).closest('form')
    if (!emailForm) throw new Error('Email form not found')
    fireEvent.change(within(emailForm).getByLabelText('New email address'), { target: { value: 'new@example.test' } })
    fireEvent.change(within(emailForm).getByLabelText('Current password'), { target: { value: 'old-password' } })
    fireEvent.submit(emailForm)
    await waitFor(() => expect(vi.mocked(requestEmailChange).mock.calls[0]?.[0]).toEqual({
      email: 'new@example.test', current_password: 'old-password',
    }))

    const sessionsForm = screen.getByRole('heading', { name: 'Sessions' }).closest('section')
    if (!sessionsForm) throw new Error('Sessions section not found')
    const sessionsInput = within(sessionsForm).getByLabelText('Current password')
    fireEvent.change(sessionsInput, { target: { value: 'old-password' } })
    fireEvent.click(within(sessionsForm).getByRole('button', { name: 'Log out of all devices' }))
    await waitFor(() => expect(vi.mocked(revokeAllSessions).mock.calls[0]?.[0]).toEqual({ current_password: 'old-password' }))

    const dangerSection = screen.getByRole('heading', { name: 'Danger zone' }).closest('section')
    if (!dangerSection) throw new Error('Danger zone section not found')
    fireEvent.change(within(dangerSection).getByLabelText('Type DELETE to confirm'), { target: { value: 'DELETE' } })
    fireEvent.change(within(dangerSection).getByLabelText('Current password'), { target: { value: 'old-password' } })
    fireEvent.click(within(dangerSection).getByRole('button', { name: 'Delete account' }))
    await waitFor(() => expect(vi.mocked(deleteMyAccount).mock.calls[0]?.[0]).toEqual({ current_password: 'old-password' }))
  })
})
