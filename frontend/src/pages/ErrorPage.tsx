import { Link } from 'react-router-dom'
import { Logo } from '../components/Logo'

export function ErrorPage() {
  return (
    <main className="not-found" role="alert">
      <Logo variant="mark" size={68} />
      <h1>Something went sideways.</h1>
      <p>We couldn’t finish loading this page. Please try again.</p>
      <Link className="button button--primary" to="/">Back home</Link>
    </main>
  )
}