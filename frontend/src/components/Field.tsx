import type { InputHTMLAttributes } from 'react'

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
}

export function Field({ label, id, error, ...inputProps }: FieldProps) {
  const fieldId = id ?? inputProps.name
  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      <input id={fieldId} aria-invalid={Boolean(error)} aria-describedby={error ? `${fieldId}-error` : undefined} {...inputProps} />
      {error && <span className="field__error" id={`${fieldId}-error`}>{error}</span>}
    </div>
  )
}