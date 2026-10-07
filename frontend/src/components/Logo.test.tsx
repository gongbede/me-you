import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Logo } from './Logo'

describe('Logo', () => {
  it('renders the accessible Me&You alt text', () => {
    render(<Logo variant="horizontal" />)
    expect(screen.getByAltText('Me&You')).toBeInTheDocument()
  })
})