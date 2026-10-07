import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { confirmEmailVerification, requestEmailVerification } from '../api/auth'
import { getFriendlyErrorMessage } from '../api/client'
import { AuthFrame } from '../components/AuthFrame'
import { useAuth } from '../hooks/useAuth'

export function VerifyEmailPage() {
  const { user } = useAuth()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function submit() {
    setError(null)
    setMessage(null)
    setLoading(true)
    try {
      const response = token
        ? await confirmEmailVerification({ token })
        : await requestEmailVerification()
      setMessage(response.message)
    } catch (reason) {
      setError(getFriendlyErrorMessage(reason))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthFrame eyebrow="One small check" title="Verify your email." intro="Keep your account details up to date and yours alone.">
      {message && <div className="form-success" role="status">{message}</div>}
      {error && <div className="form-alert" role="alert">{error}</div>}
      {token || user ? (
        <button className="button button--primary button--wide" type="button" onClick={() => void submit()} disabled={loading}>
          {loading ? 'Working…' : token ? 'Confirm email' : 'Send verification email'}
        </button>
      ) : (
        <div className="form-note">Sign in to request a verification email.</div>
      )}
      <div className="auth-links"><Link to={user ? '/' : '/login'}>{user ? 'Back home' : 'Back to sign in'}</Link></div>
    </AuthFrame>
  )
}