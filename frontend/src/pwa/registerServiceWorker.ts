export function registerServiceWorker(isProduction: boolean): void {
  if (!isProduction || !('serviceWorker' in navigator)) return

  void navigator.serviceWorker
    .register('/service-worker.js')
    .catch((error: unknown) => {
      console.error('Could not register the Me&You service worker.', error)
    })
}
