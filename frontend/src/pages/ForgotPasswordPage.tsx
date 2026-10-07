import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { requestPasswordRecovery } from '../api/auth'
import { getFriendlyErrorMessage } from '../api/client'
import { AuthFrame } from '../components/AuthFrame'
import { Field } from '../components/Field'

export function ForgotPasswordPage() {
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage(null)
    setError(null)
    setLoading(true)
    const data = new FormData(event.currentTarget)
    try {
      const response = await requestPasswordRecovery({ email: String(data.get('email') ?? '').trim() })
      setMessage(response.message)
    } catch (reason) {
      setError(getFriendlyErrorMessage(reason))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthFrame eyebrow="A fresh start" title="Reset your password." intro="We’ll send a recovery link if your account is eligible.">
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        {message && <div className="form-success" role="status">{message}</div>}
        {error && <div className="form-alert" role="alert">{error}</div>}
        <Field label="Email address" name="email" type="email" autoComplete="email" required />
        <button className="button button--primary button--wide" type="submit" disabled={loading}>
          {loading ? 'Sending…' : 'Send recovery link'}
        </button>
      </form>
      <div className="auth-links"><Link to="/login">Back to sign in</Link></div>
    </AuthFrame>
  )
}