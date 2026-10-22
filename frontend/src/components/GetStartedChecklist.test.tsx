import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { GetStartedChecklist } from './GetStartedChecklist'

describe('GetStartedChecklist', () => {
  afterEach(() => {
    cleanup()
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('remembers completed steps and dismissal for the current user', () => {
    render(<MemoryRouter><GetStartedChecklist userId="student-1" onWritePost={vi.fn()} /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Mark complete: Follow three people' }))
    expect(screen.getByText('1 of 4 complete')).toBeInTheDocument()
    expect(window.localStorage.getItem('me-you-get-started:student-1')).toContain('following')

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss Get started checklist' }))
    expect(screen.queryByRole('region', { name: 'Get started' })).not.toBeInTheDocument()
    expect(window.localStorage.getItem('me-you-get-started:student-1')).toContain('dismissed')
  })

  it('stays usable when localStorage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Unavailable') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Unavailable') })
    render(<MemoryRouter><GetStartedChecklist userId="student-2" onWritePost={vi.fn()} /></MemoryRouter>)

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss Get started checklist' }))
    expect(screen.queryByRole('region', { name: 'Get started' })).not.toBeInTheDocument()
  })
})