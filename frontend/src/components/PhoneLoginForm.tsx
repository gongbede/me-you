import { useEffect, useState, type FormEvent } from 'react'
import { Field } from './Field'

export function PhoneLoginForm({
  error,
  loading,
  onRequestCode,
  onVerify,
}: {
  error: string | null
  loading: boolean
  onRequestCode: (phoneNumber: string) => Promise<boolean>
  onVerify: (phoneNumber: string, code: string) => Promise<void>
}) {
  const [phoneNumber, setPhoneNumber] = useState('')
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [resendUntil, setResendUntil] = useState<number | null>(null)
  const [now, setNow] = useState(0)

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [])

  const resendSeconds = resendUntil === null ? 0 : Math.max(0, Math.ceil((resendUntil - now) / 1000))

  async function requestCode() {
    const normalizedInput = phoneNumber.trim()
    if (!normalizedInput || loading) return
    if (await onRequestCode(normalizedInput)) {
      const requestedAt = Date.now()
      setCodeSent(true)
      setCode('')
      setNow(requestedAt)
      setResendUntil(requestedAt + 60_000)
    }
  }

  async function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading || !codeSent) return
    await onVerify(phoneNumber.trim(), code)
  }

  return (
    <form className="auth-form" onSubmit={(event) => void submitCode(event)}>
      {error && <div className="form-alert" role="alert">{error}</div>}
      {codeSent && <p className="form-success" role="status">If the number can receive messages, a sign-in code has been sent.</p>}
      <Field
        label="Phone number"
        name="phone-number"
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        placeholder="+1 202 555 0111"
        value={phoneNumber}
        onChange={(event) => {
          if (event.target.value !== phoneNumber) {
            setCodeSent(false)
            setCode('')
          }
          setPhoneNumber(event.target.value)
        }}
        required
      />
      {codeSent && (
        <Field
          label="6-digit code"
          name="phone-code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          minLength={6}
          maxLength={6}
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
          required
        />
      )}
      {!codeSent ? (
        <button className="button button--primary button--wide" type="button" onClick={() => void requestCode()} disabled={loading || !phoneNumber.trim()}>
          {loading ? 'Sending code…' : 'Send code'}
        </button>
      ) : (
        <>
          <button className="button button--primary button--wide" type="submit" disabled={loading || code.length !== 6}>
            {loading ? 'Verifying…' : 'Verify and sign in'}
          </button>
          <button className="button button--outline button--wide" type="button" onClick={() => void requestCode()} disabled={loading || resendSeconds > 0}>
            {resendSeconds > 0 ? `Resend code in ${resendSeconds}s` : 'Resend code'}
          </button>
        </>
      )}
    </form>
  )
}