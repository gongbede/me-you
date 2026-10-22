import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { HelpPage } from './HelpPage'

describe('HelpPage', () => {
  afterEach(cleanup)

  it('shows plain-text help for the main community workflows', () => {
    render(<MemoryRouter><HelpPage /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'How do I post?' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'How do I upload a video?' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'How do I join a class?' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'How do I report something?' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'How do I install the app?' })).toBeInTheDocument()
  })
})