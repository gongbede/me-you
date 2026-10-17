import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Flag, X } from 'lucide-react'
import { getFriendlyErrorMessage } from '../api/client'
import { submitReport, type ReportReason, type ReportTargetType } from '../api/moderation'

const reasonLabels: Record<ReportReason, string> = {
  SPAM: 'Spam',
  HARASSMENT: 'Harassment',
  INAPPROPRIATE: 'Inappropriate content',
  MISINFORMATION: 'Misinformation',
  OTHER: 'Other',
}

export function ReportDialog({ targetType, targetId }: { targetType: ReportTargetType; targetId: string }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<ReportReason>('SPAM')
  const [details, setDetails] = useState('')
  const mutation = useMutation({
    mutationFn: () => submitReport({ target_type: targetType, target_id: targetId, reason, details: details.trim() || null }),
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    mutation.mutate()
  }

  function close() {
    setOpen(false)
    mutation.reset()
    setDetails('')
  }

  return (
    <>
      <button className="button button--quiet report-trigger" type="button" onClick={() => setOpen(true)}>
        <Flag size={15} aria-hidden="true" /> Report
      </button>
      {open && (
        <div className="report-dialog-backdrop">
          <section className="report-dialog" role="dialog" aria-modal="true" aria-labelledby="report-dialog-title">
            <header><h2 id="report-dialog-title">Report {targetType.toLowerCase()}</h2><button className="icon-button" type="button" onClick={close} aria-label="Close report dialog"><X size={18} aria-hidden="true" /></button></header>
            {mutation.isSuccess ? (
              <div><p role="status">Thank you. Your report has been sent to the moderation team.</p><button className="button button--primary" type="button" onClick={close}>Done</button></div>
            ) : (
              <form onSubmit={submit}>
                <label className="field"><span>Reason</span><select value={reason} onChange={(event) => setReason(event.currentTarget.value as ReportReason)}>{Object.entries(reasonLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label className="field"><span>Additional details (optional)</span><textarea value={details} maxLength={1000} rows={4} onChange={(event) => setDetails(event.currentTarget.value)} /></label>
                <p className="muted-copy">{details.length}/1000 characters. Reports are reviewed by platform moderators.</p>
                {mutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(mutation.error)}</p>}
                <div className="report-dialog__actions"><button className="button button--outline" type="button" onClick={close}>Cancel</button><button className="button button--primary" type="submit" disabled={mutation.isPending}>{mutation.isPending ? 'Sending…' : 'Send report'}</button></div>
              </form>
            )}
          </section>
        </div>
      )}
    </>
  )
}
