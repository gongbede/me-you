import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AuthFrame } from '../components/AuthFrame'
import { LoginForm } from '../components/LoginForm'
import { GoogleSignInButton } from '../components/GoogleSignInButton'
import { getFriendlyErrorMessage } from '../api/client'
import { useAuth } from '../hooks/useAuth'

export function LoginPage() {
  const { login, loginWithGoogle } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function submit(values: { email: string; password: string }) {
    setError(null)
    setLoading(true)
    try {
      await login(values)
      const destination = (location.state as { from?: string } | null)?.from ?? '/'
      navigate(destination, { replace: true })
    } catch (reason) {
      setError(getFriendlyErrorMessage(reason))
    } finally {
      setLoading(false)
    }
  }

  async function signInWithGoogle(idToken: string) {
    setError(null)
    setLoading(true)
    try {
      await loginWithGoogle(idToken)
      const destination = (location.state as { from?: string } | null)?.from ?? '/'
      navigate(destination, { replace: true })
    } catch (reason) {
      setError(getFriendlyErrorMessage(reason))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthFrame eyebrow="Welcome back" title="Good to see you." intro="Pick up where your curiosity left off.">
      <LoginForm onSubmit={submit} error={error} loading={loading} />
      <GoogleSignInButton onSignIn={signInWithGoogle} />
      <div className="auth-links auth-links--between">
        <Link to="/forgot-password">Forgot password?</Link>
        <span>New here? <Link to="/register">Create account</Link></span>
      </div>
    </AuthFrame>
  )
}