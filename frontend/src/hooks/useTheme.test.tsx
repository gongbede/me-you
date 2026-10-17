import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider, useTheme } from './useTheme'

function ThemeProbe() {
  const { choice, resolvedTheme, setChoice } = useTheme()
  return (
    <div>
      <output>{`${choice}:${resolvedTheme}`}</output>
      <button type="button" onClick={() => setChoice('dark')}>Choose dark</button>
      <button type="button" onClick={() => setChoice('light')}>Choose light</button>
    </div>
  )
}

function renderThemeProbe() {
  return render(<ThemeProvider><ThemeProbe /></ThemeProvider>)
}

describe('ThemeProvider', () => {
  let themeColor: HTMLMetaElement

  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    themeColor = document.createElement('meta')
    themeColor.name = 'theme-color'
    document.head.append(themeColor)
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  })

  afterEach(() => {
    cleanup()
    themeColor.remove()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('defaults to the system theme', async () => {
    renderThemeProbe()

    expect(await screen.findByText('system:dark')).toBeInTheDocument()
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(localStorage.getItem('me-you-theme')).toBe('system')
  })

  it('applies and persists an explicit theme selection', async () => {
    renderThemeProbe()
    fireEvent.click(screen.getByRole('button', { name: 'Choose light' }))

    expect(await screen.findByText('light:light')).toBeInTheDocument()
    expect(localStorage.getItem('me-you-theme')).toBe('light')
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute('content', '#0B6BFF')
  })

  it('keeps working when local storage is unavailable', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage unavailable') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage unavailable') })
    renderThemeProbe()

    expect(await screen.findByText('system:dark')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Choose light' }))

    expect(await screen.findByText('light:light')).toBeInTheDocument()
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })
})
