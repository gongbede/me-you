import { useState } from 'react'
import { Sparkles } from 'lucide-react'

export type LogoVariant = 'mark' | 'horizontal' | 'horizontal-white'

export function Logo({ variant = 'horizontal', size = 36 }: {
  variant?: LogoVariant
  size?: number
}) {
  const [imageFailed, setImageFailed] = useState(false)
  const src = variant === 'mark'
    ? '/brand/logo-mark.svg'
    : variant === 'horizontal-white'
      ? '/brand/logo-horizontal-white.svg'
      : '/brand/logo-horizontal.svg'

  if (imageFailed) {
    return (
      <span className={`logo logo--${variant}`} role="img" aria-label="Me&You" style={{ height: size }}>
        {variant === 'mark' ? <Sparkles size={size * 0.52} aria-hidden="true" /> : <span>Me&You</span>}
      </span>
    )
  }

  return (
    <img
      className={`logo logo--${variant}`}
      src={src}
      alt="Me&You"
      height={size}
      width={variant === 'mark' ? size : undefined}
      onError={() => setImageFailed(true)}
    />
  )
}