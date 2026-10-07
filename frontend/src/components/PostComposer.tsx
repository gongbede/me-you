import { useState, type FormEvent } from 'react'
import { Send } from 'lucide-react'
import { isValidPostContent, MAX_POST_LENGTH } from './feedHelpers'

export function PostComposer({
  onPost,
  isPosting,
  error,
}: {
  onPost: (content: string) => Promise<void>
  isPosting: boolean
  error: string | null
}) {
  const [content, setContent] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!isValidPostContent(content)) return
    try {
      await onPost(content.trim())
      setContent('')
    } catch {
      return
    }
  }

  return (
    <form className="post-composer" onSubmit={(event) => void submit(event)}>
      <label htmlFor="post-content">Share something with your community</label>
      <textarea
        id="post-content"
        name="content"
        rows={3}
        value={content}
        onChange={(event) => setContent(event.currentTarget.value)}
        placeholder="What have you been learning?"
        aria-describedby="post-character-count"
      />
      <div className="post-composer__footer">
        <span id="post-character-count" aria-live="polite">{Array.from(content).length.toLocaleString()} / {MAX_POST_LENGTH.toLocaleString()}</span>
        <button className="button button--primary" type="submit" disabled={!isValidPostContent(content) || isPosting}>
          <Send size={16} aria-hidden="true" /> {isPosting ? 'Posting…' : 'Post'}
        </button>
      </div>
      {error && <p className="form-alert" role="alert">{error}</p>}
    </form>
  )
}