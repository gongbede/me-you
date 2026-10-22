import { Link } from 'react-router-dom'

export function AppFooter() {
  return (
    <footer className="app-footer">
      <span>Me&You · Learn. Connect. Grow.</span>
      <nav aria-label="Footer navigation">
        <Link to="/privacy">Privacy</Link>
        <Link to="/terms">Terms</Link>
        <Link to="/contact">Contact</Link>
      </nav>
    </footer>
  )
}