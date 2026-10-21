import { afterEach, describe, expect, it, vi } from 'vitest'

import { createComment, createPost, getFeed, setCommentLike, updatePost } from './social'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('social API helpers', () => {
  it('requests a selected feed mode and cursor', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], offset: 0, limit: 20, has_more: false }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await getFeed('after-token', 'LATEST')

    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/posts/feed?limit=20&mode=LATEST&cursor=after-token',
    )
  })

  it('sends typed image, edit, and reply payloads', async () => {
    const fetchMock = vi.fn().mockImplementation(
      () => Promise.resolve(new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createPost('A post', [{ media_asset_id: 'image-id', alt_text: 'Alt' }])
    await updatePost('post-id', {
      content: 'Edited',
      attachments: [],
    })
    await createComment('post-id', 'Reply', 'parent-id')
    await setCommentLike('comment-id', true)

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      content: 'A post',
      attachments: [{ media_asset_id: 'image-id', alt_text: 'Alt' }],
    })
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      content: 'Edited',
      attachments: [],
    })
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      content: 'Reply',
      parent_id: 'parent-id',
    })
    expect(fetchMock.mock.calls[3][0]).toBe('/api/v1/comments/comment-id/like')
    expect(fetchMock.mock.calls[3][1].method).toBe('POST')
  })
})