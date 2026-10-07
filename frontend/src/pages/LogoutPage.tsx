import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import { AuthFrame } from '../components/AuthFrame'
import { useAuth } from '../hooks/useAuth'

export function LogoutPage() {
  const { logout, user } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function finishLogout() {
    setLoading(true)
    setError(null)
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch (reason) {
      setError(getFriendlyErrorMessage(reason))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthFrame eyebrow="Until next time" title="Leaving already?" intro={user ? `Signed in as ${user.email}` : 'Your session is ready to close.'}>
      {error && <div className="form-alert" role="alert">{error}</div>}
      <button className="button button--primary button--wide" type="button" onClick={() => void finishLogout()} disabled={loading}>
        {loading ? 'Signing out…' : 'Sign out'}
      </button>
      <div className="auth-links"><Link to="/">Stay a little longer</Link></div>
    </AuthFrame>
  )
}