import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AuthFrame } from '../components/AuthFrame'
import { LoginForm } from '../components/LoginForm'
import { GoogleSignInButton } from '../components/GoogleSignInButton'
import { PhoneLoginForm } from '../components/PhoneLoginForm'
import { getFriendlyErrorMessage } from '../api/client'
import { requestPhoneLoginCode } from '../api/auth'
import { useAuth } from '../hooks/useAuth'

export function LoginPage() {
  const { login, loginWithGoogle, loginWithPhone } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [method, setMethod] = useState<'email' | 'phone'>('email')

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

  async function requestPhoneCode(phoneNumber: string): Promise<boolean> {
    setError(null)
    setLoading(true)
    try {
      await requestPhoneLoginCode(phoneNumber)
      return true
    } catch (reason) {
      setError(getFriendlyErrorMessage(reason))
      return false
    } finally {
      setLoading(false)
    }
  }

  async function verifyPhone(phoneNumber: string, code: string) {
    setError(null)
    setLoading(true)
    try {
      await loginWithPhone(phoneNumber, code)
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
      <div className="auth-method-switch" role="group" aria-label="Sign-in method">
        <button type="button" aria-pressed={method === 'email'} onClick={() => { setMethod('email'); setError(null) }}>Email</button>
        <button type="button" aria-pressed={method === 'phone'} onClick={() => { setMethod('phone'); setError(null) }}>Phone</button>
      </div>
      {method === 'email'
        ? <LoginForm onSubmit={submit} error={error} loading={loading} />
        : <PhoneLoginForm error={error} loading={loading} onRequestCode={requestPhoneCode} onVerify={verifyPhone} />}
      <GoogleSignInButton onSignIn={signInWithGoogle} />
      <div className="auth-links auth-links--between">
        <Link to="/forgot-password">Forgot password?</Link>
        <span>New here? <Link to="/register">Create account</Link></span>
      </div>
    </AuthFrame>
  )
}