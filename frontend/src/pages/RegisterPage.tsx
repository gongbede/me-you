import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import { AuthFrame } from '../components/AuthFrame'
import { Field } from '../components/Field'
import { GoogleSignInButton } from '../components/GoogleSignInButton'
import { useAuth } from '../hooks/useAuth'

export function RegisterPage() {
  const { loginWithGoogle, register } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const password = String(data.get('password') ?? '')
    const confirmation = String(data.get('confirmation') ?? '')
    if (password !== confirmation) {
      setError('Those passwords do not match yet.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      await register({
        username: String(data.get('username') ?? '').trim(),
        email: String(data.get('email') ?? '').trim(),
        password,
      })
      navigate('/login', { replace: true, state: { registered: true } })
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
      navigate('/', { replace: true })
    } catch (reason) {
      setError(getFriendlyErrorMessage(reason))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthFrame eyebrow="Make a little space" title="Start with a hello." intro="Create an account and find your people.">
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        {error && <div className="form-alert" role="alert">{error}</div>}
        <Field label="Your name" name="username" autoComplete="username" minLength={3} maxLength={50} required />
        <Field label="Email address" name="email" type="email" autoComplete="email" required />
        <Field label="Password" name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} required />
        <Field label="Confirm password" name="confirmation" type="password" autoComplete="new-password" minLength={8} required />
        <button className="button button--primary button--wide" type="submit" disabled={loading}>
          {loading ? 'Creating your account…' : 'Create account'}
        </button>
      </form>
      <GoogleSignInButton onSignIn={signInWithGoogle} />
      <div className="auth-links"><span>Already have an account? <Link to="/login">Sign in</Link></span></div>
    </AuthFrame>
  )
}