import { Sparkles } from 'lucide-react'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? 'brand--compact' : ''}`} aria-label="Me&You">
      <span className="brand__mark" aria-hidden="true">
        <Sparkles size={19} strokeWidth={2.4} />
      </span>
      <span className="brand__wordmark">Me<span>&</span>You</span>
      {!compact && <span className="brand__tagline">Learn. Connect. Grow.</span>}
    </div>
  )
}