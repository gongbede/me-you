import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { InstallPromptBanner } from './InstallPromptBanner'

const dismissedKey = 'me-you-install-banner-dismissed'

function createInstallEvent() {
  return Object.assign(
    new Event('beforeinstallprompt', { cancelable: true }),
    {
      prompt: vi.fn().mockResolvedValue(undefined),
      userChoice: Promise.resolve({ outcome: 'accepted' as const, platform: 'web' }),
    },
  )
}

describe('InstallPromptBanner', () => {
  afterEach(() => cleanup())
  beforeEach(() => window.localStorage.removeItem(dismissedKey))

  it('appears only after the browser signals that installation is available', () => {
    render(<InstallPromptBanner />)

    expect(screen.queryByText('Install Me&You')).not.toBeInTheDocument()
    act(() => {
      window.dispatchEvent(createInstallEvent())
    })

    expect(screen.getByText('Install Me&You')).toBeInTheDocument()
  })

  it('remembers dismissal and invokes the browser install prompt', async () => {
    const firstRender = render(<InstallPromptBanner />)
    const event = createInstallEvent()
    act(() => {
      window.dispatchEvent(event)
    })
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss install prompt' }))

    expect(window.localStorage.getItem(dismissedKey)).toBe('true')
    expect(screen.queryByText('Install Me&You')).not.toBeInTheDocument()

    firstRender.unmount()
    render(<InstallPromptBanner />)
    act(() => {
      window.dispatchEvent(createInstallEvent())
    })
    expect(screen.queryByText('Install Me&You')).not.toBeInTheDocument()

    window.localStorage.removeItem(dismissedKey)
    cleanup()
    const installEvent = createInstallEvent()
    render(<InstallPromptBanner />)
    act(() => {
      window.dispatchEvent(installEvent)
    })
    fireEvent.click(screen.getByRole('button', { name: 'Install' }))
    await waitFor(() => expect(installEvent.prompt).toHaveBeenCalledOnce())
    expect(await screen.queryByText('Install Me&You')).not.toBeInTheDocument()
  })
})
