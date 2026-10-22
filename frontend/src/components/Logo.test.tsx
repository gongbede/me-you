import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ThemeProvider } from '../hooks/useTheme'
import { Logo } from './Logo'

describe('Logo', () => {
  afterEach(() => {
    cleanup()
    window.localStorage.removeItem('me-you-theme')
  })

  it('renders the accessible Me&You alt text', () => {
    render(<ThemeProvider><Logo variant="horizontal" /></ThemeProvider>)
    expect(screen.getByAltText('Me&You')).toBeInTheDocument()
  })

  it.each([
    ['light', '/brand/logo-horizontal.svg'],
    ['dark', '/brand/logo-horizontal-white.svg'],
  ] as const)('uses the %s horizontal logo in that theme', (theme, expectedSource) => {
    window.localStorage.setItem('me-you-theme', theme)
    render(<ThemeProvider><Logo variant="horizontal" /></ThemeProvider>)
    expect(screen.getByAltText('Me&You')).toHaveAttribute('src', expectedSource)
  })
})