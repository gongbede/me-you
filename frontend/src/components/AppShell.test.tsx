import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getTeachingCourses } from '../api/education'
import { AppShell } from './AppShell'

vi.mock('../api/education', () => ({ getTeachingCourses: vi.fn() }))
vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { username: 'teacher', email: 'teacher@example.test' } }),
}))

const getCourses = vi.mocked(getTeachingCourses)

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
  beforeEach(() => getCourses.mockReset())

  it('offers a retry when course lookup fails and restores Teaching on success', async () => {
    getCourses.mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce([{ id: 'course-1' }] as never)
    renderAppShell()

    const mainNavigation = screen.getByRole('complementary', { name: 'Main navigation' })
    const retry = await within(mainNavigation).findByRole('button', { name: 'Retry Teaching' })
    fireEvent.click(retry)

    expect(await within(mainNavigation).findByRole('link', { name: 'Teaching' })).toBeInTheDocument()
    expect(getCourses).toHaveBeenCalledTimes(2)
  })
})