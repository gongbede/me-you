import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createComment, deleteComment, getCommentsPage, setCommentLike, updateComment } from '../api/social'
import type { Comment } from '../api/social'
import { CommentsSection } from './CommentsSection'
import { renderCommentContent } from './commentText'

vi.mock('../api/social', () => ({
  createComment: vi.fn(),
  deleteComment: vi.fn(),
  getCommentsPage: vi.fn(),
  setCommentLike: vi.fn(),
  updateComment: vi.fn(),
}))

const rootComment: Comment = {
  id: 'comment-1',
  author: { id: 'author-1', username: 'author' },
  author_id: 'author-1',
  content: 'Great work',
  created_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-20T10:00:00Z',
  like_count: 0,
  liked_by_me: false,
  parent_id: null,
  post_id: 'post-1',
}

function renderComments() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><CommentsSection postId="post-1" currentUserId="viewer-1" onCommentsChanged={vi.fn()} /></MemoryRouter></QueryClientProvider>)
}

describe('CommentsSection interactions', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })
  beforeEach(() => {
    vi.mocked(getCommentsPage).mockReset().mockResolvedValue({ items: [rootComment], nextCursor: null })
    vi.mocked(createComment).mockReset()
    vi.mocked(setCommentLike).mockReset()
  })

  it('shows a new comment optimistically and rolls it back after failure', async () => {
    let rejectRequest: ((error: Error) => void) | undefined
    vi.mocked(createComment).mockImplementation(() => new Promise((_resolve, reject) => { rejectRequest = reject }))
    renderComments()
    expect(await screen.findByText('Great work')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Write a comment' }), { target: { value: 'My reply' } })
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    await waitFor(() => expect(screen.getAllByText('My reply')).toHaveLength(2))
    rejectRequest?.(new Error('Comment unavailable'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Comment unavailable')
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Write a comment' })).toHaveValue('My reply'))
    expect(screen.getAllByText('My reply')).toHaveLength(1)
  })

  it('submits a one-level reply to its parent', async () => {
    vi.mocked(createComment).mockResolvedValue({ ...rootComment, id: 'reply-1', content: 'Agreed', parent_id: 'comment-1' })
    renderComments()
    fireEvent.click(await screen.findByRole('button', { name: 'Reply' }))
    expect(screen.getByPlaceholderText('Reply to @author…')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Write a comment' }), { target: { value: 'Agreed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Comment' }))
    await waitFor(() => expect(createComment).toHaveBeenCalledWith('post-1', 'Agreed', 'comment-1'))
  })

  it('rolls an optimistic comment like back on failure', async () => {
    let rejectRequest: ((error: Error) => void) | undefined
    vi.mocked(setCommentLike).mockImplementation(() => new Promise((_resolve, reject) => { rejectRequest = reject }))
    renderComments()
    fireEvent.click(await screen.findByRole('button', { name: 'Like comment, 0 likes' }))
    expect(await screen.findByRole('button', { name: 'Unlike comment, 1 likes' })).toBeInTheDocument()
    rejectRequest?.(new Error('Like unavailable'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Like unavailable')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Like comment, 0 likes' })).toBeInTheDocument())
  })

  it('edits and confirms deletion of an owned comment', async () => {
    const ownComment = { ...rootComment, author_id: 'viewer-1', author: { id: 'viewer-1', username: 'viewer' } }
    vi.mocked(getCommentsPage).mockResolvedValue({ items: [ownComment], nextCursor: null })
    vi.mocked(updateComment).mockResolvedValue({ ...ownComment, content: 'Updated note' })
    vi.mocked(deleteComment).mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderComments()

    expect(await screen.findByText('Great work')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit comment' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Edit comment' }), { target: { value: 'Updated note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))
    await waitFor(() => expect(updateComment).toHaveBeenCalledWith('comment-1', 'Updated note'))
    await waitFor(() => expect(screen.queryByRole('textbox', { name: 'Edit comment' })).not.toBeInTheDocument())
    expect(screen.getByText('Updated note')).toBeInTheDocument()
    expect(updateComment).toHaveBeenCalledWith('comment-1', 'Updated note')

    fireEvent.click(screen.getByRole('button', { name: 'Delete comment' }))
    expect(window.confirm).toHaveBeenCalledWith('Delete this comment?')
    await waitFor(() => expect(deleteComment).toHaveBeenCalledWith('comment-1', expect.objectContaining({ client: expect.anything() })))
  })
})

describe('safe comment mentions', () => {
  it('links encoded handles and keeps markup as text', () => {
    render(<MemoryRouter><p>{renderCommentContent('Hi @classmate <img src=x onerror=alert(1)>')}</p></MemoryRouter>)
    expect(screen.getByRole('link', { name: '@classmate' })).toHaveAttribute('href', '/search?q=classmate')
    expect(screen.getByText((_text, element) => element?.tagName === 'P' && element.textContent?.includes('<img src=x onerror=alert(1)>') === true)).toBeInTheDocument()
  })
})