import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getNotificationPreferences,
  updateNotificationPreferences,
} from '../api/notifications'
import { SettingsPage } from './SettingsPage'

vi.mock('../api/notifications', () => ({
  getNotificationPreferences: vi.fn(),
  updateNotificationPreferences: vi.fn(),
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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><SettingsPage /></MemoryRouter></QueryClientProvider>)
}

describe('SettingsPage', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    vi.mocked(getNotificationPreferences).mockResolvedValue({ preferences })
    vi.mocked(updateNotificationPreferences).mockResolvedValue({
      preferences: { ...preferences, FOLLOW: false },
    })
  })

  it('loads and saves notification preferences', async () => {
    renderPage()

    const followToggle = await screen.findByRole('checkbox', { name: 'Toggle new followers notifications' })
    expect(followToggle).toBeChecked()
    fireEvent.click(followToggle)

    await waitFor(() => expect(vi.mocked(updateNotificationPreferences).mock.calls[0]?.[0]).toEqual({
      preferences: { FOLLOW: false },
    }))
    expect(await screen.findByRole('status')).toHaveTextContent('Notification preferences saved.')
    expect(followToggle).not.toBeChecked()
  })

  it('shows a loading state while preferences are being fetched', () => {
    vi.mocked(getNotificationPreferences).mockReturnValueOnce(new Promise(() => undefined))
    renderPage()

    expect(screen.getByRole('status')).toHaveTextContent('Loading notification preferences')
  })
})
