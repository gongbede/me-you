import { useState, type FormEvent } from 'react'
import { Field } from './Field'

export interface LoginFormValues {
  email: string
  password: string
}

export function LoginForm({ onSubmit, error, loading }: {
  onSubmit: (values: LoginFormValues) => Promise<void>
  error: string | null
  loading: boolean
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await onSubmit({ email: email.trim(), password })
  }

  return (
    <form className="auth-form" onSubmit={(event) => void handleSubmit(event)}>
      {error && <div className="form-alert" role="alert">{error}</div>}
      <Field
        label="Email address"
        name="email"
        type="email"
        autoComplete="email"
        placeholder="you@example.com"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        required
      />
      <Field
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        placeholder="At least 8 characters"
        minLength={8}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />
      <button className="button button--primary button--wide" type="submit" disabled={loading}>
        {loading ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}