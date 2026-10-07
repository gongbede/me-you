import { Link } from 'react-router-dom'
import { Brand } from '../components/Brand'

export function NotFoundPage() {
  return (
    <main className="not-found">
      <Brand compact />
      <span className="not-found__code">404</span>
      <h1>This page wandered off.</h1>
      <p>That address doesn’t lead anywhere just yet.</p>
      <Link className="button button--primary" to="/">Back to your space</Link>
    </main>
  )
}