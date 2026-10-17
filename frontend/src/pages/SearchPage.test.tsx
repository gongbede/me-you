import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { search } from '../api/search'
import { SearchPage } from './SearchPage'

vi.mock('../api/search', () => ({ search: vi.fn() }))

const response = {
  query: 'river',
  items: [
    { id: 'person-1', resource_type: 'person', name: 'River Learner', code: 'river', institution_id: null },
    { id: 'post-1', resource_type: 'post', name: 'A river post', code: null, institution_id: null },
    { id: 'school-1', resource_type: 'school', name: 'River School', code: null, institution_id: 'school-1' },
  ],
  offset: 0,
  limit: 100,
  has_more: false,
  next_cursor: null,
}

function renderSearch(path = '/search') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/search" element={<SearchPage />} /></Routes></MemoryRouter></QueryClientProvider>)
}

describe('SearchPage', () => {
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('shows the minimum query prompt and switches among the result tabs', async () => {
    vi.mocked(search).mockResolvedValue(response)
    renderSearch()
    expect(screen.getByText('Enter at least 2 characters to search.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Search people, posts, and schools' }), { target: { value: 'river' } })
    await waitFor(() => expect(search).toHaveBeenCalledWith('river', 0))
    expect(await screen.findByText('River Learner')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Posts' }))
    expect(screen.getByText('A river post')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Schools' }))
    expect(screen.getByText('River School')).toBeInTheDocument()
  })

  it('reports an empty result state', async () => {
    vi.mocked(search).mockResolvedValue({ ...response, items: [] })
    renderSearch('/search?q=missing')
    expect(await screen.findByText('No results found.')).toBeInTheDocument()
  })

  it('waits for a pause in typing and sends only the final query', async () => {
    vi.useFakeTimers()
    vi.mocked(search).mockResolvedValue(response)
    renderSearch()
    const input = screen.getByRole('textbox', { name: 'Search people, posts, and schools' })
    fireEvent.change(input, { target: { value: 'ri' } })
    fireEvent.change(input, { target: { value: 'river' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(299) })
    expect(search).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(search).toHaveBeenCalledTimes(1)
    expect(search).toHaveBeenCalledWith('river', 0)
  })
})
