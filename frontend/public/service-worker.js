const CACHE_PREFIX = 'me-you-shell-'
const CACHE_NAME = `${CACHE_PREFIX}v1`
const OFFLINE_PATH = '/offline.html'

function isExcludedPath(pathname) {
  return (
    pathname === '/api' ||
    pathname.startsWith('/api/') ||
    pathname.startsWith('/media/') ||
    pathname.startsWith('/uploads/') ||
    pathname.startsWith('/storage/')
  )
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME)
    const rootRequest = new Request('/', { credentials: 'omit' })
    const rootResponse = await fetch(rootRequest)
    if (!rootResponse.ok) throw new Error('The app shell could not be cached.')
    await cache.put('/', rootResponse.clone())

    const indexHtml = await rootResponse.text()
    const assetPaths = new Set(
      [...indexHtml.matchAll(/(?:src|href)=["'](\/(?:assets|brand)\/[^"']+)["']/g)]
        .map((match) => match[1]),
    )
    const cssPaths = [...assetPaths].filter((path) => path.endsWith('.css'))
    const assetRequests = [...assetPaths].map(
      (path) => new Request(path, { credentials: 'omit' }),
    )
    await cache.addAll([
      ...assetRequests,
      new Request(OFFLINE_PATH, { credentials: 'omit' }),
    ])

    const fontPaths = new Set()
    for (const path of cssPaths) {
      const response = await cache.match(path)
      if (!response) continue
      const cssText = await response.text()
      for (const match of cssText.matchAll(/url\(["']?(\/assets\/[^"')]+)["']?\)/g)) {
        fontPaths.add(match[1])
      }
    }
    await cache.addAll(
      [...fontPaths].map((path) => new Request(path, { credentials: 'omit' })),
    )
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys()
    await Promise.all(
      cacheNames
        .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
        .map((name) => caches.delete(name)),
    )
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (
    url.origin !== self.location.origin ||
    isExcludedPath(url.pathname) ||
    request.headers.has('authorization') ||
    request.credentials === 'include'
  ) {
    return
  }

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        return await fetch(request)
      } catch {
        const cache = await caches.open(CACHE_NAME)
        if (url.pathname === '/' || url.pathname === '/index.html') {
          const appShell = await cache.match('/')
          if (appShell) return appShell
        }
        const offlinePage = await cache.match('/offline.html')
        return offlinePage ?? Response.error()
      }
    })())
    return
  }

  if (!url.pathname.startsWith('/assets/') && !url.pathname.startsWith('/brand/')) return

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME)
    const cached = await cache.match(request)
    if (cached) return cached

    const response = await fetch(new Request(request, { credentials: 'omit' }))
    if (response.ok && response.type === 'basic') {
      await cache.put(request, response.clone())
    }
    return response
  })())
})
