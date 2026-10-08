import { useEffect, useRef, useState } from 'react'
import { apiRequest } from '../api/client'

interface GoogleCredentialResponse {
  credential: string
}

interface GoogleIdentityApi {
  accounts: {
    id: {
      initialize: (options: {
        client_id: string
        callback: (response: GoogleCredentialResponse) => void
      }) => void
      renderButton: (
        parent: HTMLElement,
        options: { theme: 'outline'; size: 'large'; width: number; text: 'continue_with' },
      ) => void
    }
  }
}

declare global {
  interface Window {
    google?: GoogleIdentityApi
  }
}

export function GoogleSignInButton({ onSignIn }: { onSignIn: (idToken: string) => Promise<void> }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const signInRef = useRef(onSignIn)
  const [clientId, setClientId] = useState<string | null>(null)
  const [scriptError, setScriptError] = useState(false)

  useEffect(() => {
    signInRef.current = onSignIn
  }, [onSignIn])

  useEffect(() => {
    let active = true
    void apiRequest<{ client_id: string }>('/api/v1/auth/google/config', { auth: false })
      .then((config) => {
        if (active && config.client_id) setClientId(config.client_id)
      })
      .catch(() => {
        if (active) setClientId(null)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!clientId || !container) return

    let active = true
    const render = () => {
      if (!active || !window.google || !containerRef.current) return
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => {
          if (response.credential) void signInRef.current(response.credential)
        },
      })
      window.google.accounts.id.renderButton(containerRef.current, {
        theme: 'outline',
        size: 'large',
        width: Math.min(400, Math.max(180, Math.floor(containerRef.current.clientWidth))),
        text: 'continue_with',
      })
    }

    let script = document.querySelector<HTMLScriptElement>('script[data-google-identity-services]')
    const handleLoad = () => render()
    const handleError = () => setScriptError(true)
    if (window.google) {
      render()
    } else if (script) {
      script.addEventListener('load', handleLoad)
      script.addEventListener('error', handleError)
    } else {
      script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      script.dataset.googleIdentityServices = 'true'
      script.addEventListener('load', handleLoad)
      script.addEventListener('error', handleError)
      document.head.appendChild(script)
    }

    return () => {
      active = false
      script?.removeEventListener('load', handleLoad)
      script?.removeEventListener('error', handleError)
    }
  }, [clientId])

  if (!clientId) return null
  return (
    <div className="google-sign-in" role="group" aria-label="Continue with Google">
      {scriptError && <p className="form-alert" role="alert">Google sign-in is temporarily unavailable.</p>}
      <div ref={containerRef} />
    </div>
  )
}