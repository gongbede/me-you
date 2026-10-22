import { Link } from 'react-router-dom'

export function renderCommentContent(content: string) {
  return content.split(/(@[A-Za-z0-9_.-]{1,32})/g).map((part, index) => {
    if (!part.startsWith('@')) return part
    return <Link key={`${part}-${index}`} to={`/search?q=${encodeURIComponent(part.slice(1))}`}>{part}</Link>
  })
}