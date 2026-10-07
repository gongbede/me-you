import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Logo } from './Logo'
import { useAuth } from '../hooks/useAuth'

export function ProtectedRoute() {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <main className="splash-screen" role="status">
        <Logo variant="mark" size={72} />
        <span className="sr-only">Checking your session</span>
      </main>
    )
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}