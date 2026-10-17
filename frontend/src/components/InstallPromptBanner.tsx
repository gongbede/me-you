import { useEffect, useState } from 'react'
import { Download, X } from 'lucide-react'

const DISMISSED_KEY = 'me-you-install-banner-dismissed'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

export function InstallPromptBanner() {
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null)
  const [dismissed, setDismissed] = useState(
    () => window.localStorage.getItem(DISMISSED_KEY) === 'true',
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    function handleBeforeInstallPrompt(event: Event) {
      event.preventDefault()
      if (!dismissed) setInstallEvent(event as BeforeInstallPromptEvent)
    }

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
    return () => window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt)
  }, [dismissed])

  async function installApp() {
    if (!installEvent) return
    setError(null)
    try {
      await installEvent.prompt()
      await installEvent.userChoice
      setInstallEvent(null)
    } catch {
      setError('The install prompt could not be opened. Please try again later.')
      setInstallEvent(null)
    }
  }

  function dismissBanner() {
    window.localStorage.setItem(DISMISSED_KEY, 'true')
    setDismissed(true)
    setInstallEvent(null)
  }

  if (!installEvent || dismissed) return null

  return (
    <aside className="install-prompt-banner" aria-label="Install Me&You">
      <div className="install-prompt-banner__copy">
        <strong>Install Me&You</strong>
        <span>Keep learning close at hand.</span>
      </div>
      <div className="install-prompt-banner__actions">
        <button className="button button--primary" type="button" onClick={() => void installApp()}>
          <Download size={16} aria-hidden="true" /> Install
        </button>
        <button className="icon-button" type="button" aria-label="Dismiss install prompt" onClick={dismissBanner}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      {error && <p className="form-alert" role="alert">{error}</p>}
    </aside>
  )
}
