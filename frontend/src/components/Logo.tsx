import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { useOptionalTheme } from '../hooks/useTheme'

export type LogoVariant = 'mark' | 'horizontal' | 'horizontal-white'

export function Logo({ variant = 'horizontal', size = 36 }: {
  variant?: LogoVariant
  size?: number
}) {
  const [imageFailed, setImageFailed] = useState(false)
  const theme = useOptionalTheme()
  const resolvedTheme = theme?.resolvedTheme ?? (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')
  const displayVariant = variant === 'horizontal' && resolvedTheme === 'dark'
    ? 'horizontal-white'
    : variant
  const src = displayVariant === 'mark'
    ? '/brand/logo-mark.svg'
    : displayVariant === 'horizontal-white'
      ? '/brand/logo-horizontal-white.svg'
      : '/brand/logo-horizontal.svg'

  if (imageFailed) {
    return (
      <span className={`logo logo--${displayVariant}`} role="img" aria-label="Me&You" style={{ height: size }}>
        {displayVariant === 'mark' ? <Sparkles size={size * 0.52} aria-hidden="true" /> : <span>Me&You</span>}
      </span>
    )
  }

  return (
    <img
      className={`logo logo--${displayVariant}`}
      src={src}
      alt="Me&You"
      height={size}
      width={variant === 'mark' ? size : undefined}
      onError={() => setImageFailed(true)}
    />
  )
}