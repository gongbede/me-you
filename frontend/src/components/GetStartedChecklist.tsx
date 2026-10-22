import { Check, ChevronRight, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'

const items = [
  { id: 'profile', title: 'Complete your profile', href: '/profile' },
  { id: 'following', title: 'Follow three people', href: '/search' },
  { id: 'post', title: 'Write your first post', href: '#post-content' },
  { id: 'course', title: 'Explore a course', href: '/my-courses' },
] as const

type ChecklistItemId = (typeof items)[number]['id']
type ChecklistState = { completed: ChecklistItemId[]; dismissed: boolean }

function readChecklist(key: string): ChecklistState {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(key) ?? '{}')
    if (typeof value !== 'object' || value === null) return { completed: [], dismissed: false }
    const record = value as { completed?: unknown; dismissed?: unknown }
    const completed = Array.isArray(record.completed)
      ? record.completed.filter((id): id is ChecklistItemId => items.some((item) => item.id === id))
      : []
    return { completed, dismissed: record.dismissed === true }
  } catch {
    return { completed: [], dismissed: false }
  }
}

export function GetStartedChecklist({ userId, onWritePost }: { userId: string; onWritePost: () => void }) {
  const storageKey = `me-you-get-started:${userId}`
  const [state, setState] = useState(() => readChecklist(storageKey))

  function updateState(next: ChecklistState) {
    setState(next)
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(next))
    } catch {
      // Keep checklist state usable for this session when storage is unavailable.
    }
  }

  if (state.dismissed) return null
  return (
    <section className="get-started-card" aria-labelledby="get-started-title">
      <div className="get-started-card__heading">
        <div><span className="eyebrow">A FEW FIRST STEPS</span><h2 id="get-started-title">Get started</h2></div>
        <button className="icon-button" type="button" aria-label="Dismiss Get started checklist" title="Dismiss checklist" onClick={() => updateState({ ...state, dismissed: true })}><X size={17} aria-hidden="true" /></button>
      </div>
      <ol className="get-started-list">
        {items.map((item) => {
          const complete = state.completed.includes(item.id)
          const markComplete = () => updateState({ ...state, completed: complete ? state.completed.filter((id) => id !== item.id) : [...state.completed, item.id] })
          return <li className={complete ? 'is-complete' : ''} key={item.id}>
            <button className="get-started-list__check" type="button" aria-pressed={complete} aria-label={`${complete ? 'Mark incomplete' : 'Mark complete'}: ${item.title}`} onClick={markComplete}>{complete && <Check size={15} aria-hidden="true" />}</button>
            {item.id === 'post'
              ? <button className="get-started-list__link" type="button" onClick={onWritePost}><span>{item.title}</span><ChevronRight size={16} aria-hidden="true" /></button>
              : <Link className="get-started-list__link" to={item.href}><span>{item.title}</span><ChevronRight size={16} aria-hidden="true" /></Link>}
          </li>
        })}
      </ol>
      <p className="get-started-card__progress" aria-live="polite">{state.completed.length} of {items.length} complete</p>
    </section>
  )
}