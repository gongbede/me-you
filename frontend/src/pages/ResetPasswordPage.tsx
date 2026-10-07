import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { confirmPasswordRecovery } from '../api/auth'
import { getFriendlyErrorMessage } from '../api/client'
import { AuthFrame } from '../components/AuthFrame'
import { Field } from '../components/Field'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const newPassword = String(data.get('password') ?? '')
    if (newPassword !== String(data.get('confirmation') ?? '')) {
      setError('Those passwords do not match yet.')
      return
    }
    setError(null)
    setMessage(null)
    setLoading(true)
    try {
      const response = await confirmPasswordRecovery({ token, new_password: newPassword })
      setMessage(response.message)
    } catch (reason) {
      setError(getFriendlyErrorMessage(reason))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthFrame eyebrow="A fresh start" title="Choose a new password." intro="Use the recovery token from your email to continue.">
      {!token ? (
        <div className="form-alert" role="alert">This reset link is missing its token. Request a new one to continue.</div>
      ) : (
        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          {message && <div className="form-success" role="status">{message}</div>}
          {error && <div className="form-alert" role="alert">{error}</div>}
          <Field label="New password" name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} required />
          <Field label="Confirm new password" name="confirmation" type="password" autoComplete="new-password" minLength={8} required />
          <button className="button button--primary button--wide" type="submit" disabled={loading}>
            {loading ? 'Updating…' : 'Update password'}
          </button>
        </form>
      )}
      <div className="auth-links"><Link to="/login">Back to sign in</Link></div>
    </AuthFrame>
  )
}