/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeChoice = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

interface ThemeContextValue {
  choice: ThemeChoice
  resolvedTheme: ResolvedTheme
  setChoice: (choice: ThemeChoice) => void
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

function readThemeChoice(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem('me-you-theme')
    return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
  } catch {
    return 'system'
  }
}

function systemTheme(): ResolvedTheme {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

function applyTheme(theme: ResolvedTheme) {
  document.documentElement.dataset.theme = theme
  const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  if (themeColor) themeColor.content = theme === 'dark' ? '#0B1F44' : '#0B6BFF'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoice] = useState<ThemeChoice>(readThemeChoice)
  const [systemPreference, setSystemPreference] = useState<ResolvedTheme>(systemTheme)
  const resolvedTheme = choice === 'system' ? systemPreference : choice

  useEffect(() => {
    applyTheme(resolvedTheme)
    try {
      window.localStorage.setItem('me-you-theme', choice)
    } catch {
      // The selected theme remains active for this session if storage is unavailable.
    }
  }, [choice, resolvedTheme])

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const preference = window.matchMedia('(prefers-color-scheme: dark)')
    const updatePreference = (event: MediaQueryListEvent) => setSystemPreference(event.matches ? 'dark' : 'light')
    preference.addEventListener?.('change', updatePreference)
    return () => preference.removeEventListener?.('change', updatePreference)
  }, [])

  const value = useMemo<ThemeContextValue>(() => ({
    choice,
    resolvedTheme,
    setChoice,
    toggleTheme: () => setChoice(resolvedTheme === 'dark' ? 'light' : 'dark'),
  }), [choice, resolvedTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useOptionalTheme() {
  return useContext(ThemeContext)
}

export function useTheme() {
  const context = useOptionalTheme()
  if (!context) throw new Error('useTheme must be used inside ThemeProvider')
  return context
}
