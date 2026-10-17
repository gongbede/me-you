import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cwd } from 'node:process'
import { runInNewContext } from 'node:vm'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { registerServiceWorker } from './registerServiceWorker'

const publicDirectory = resolve(cwd(), 'public')

describe('PWA static assets', () => {
  it('declares the required app identity, display, colors, and brand icons', () => {
    const manifest = JSON.parse(readFileSync(resolve(publicDirectory, 'manifest.webmanifest'), 'utf8')) as {
      name: string
      short_name: string
      description: string
      theme_color: string
      background_color: string
      display: string
      start_url: string
      scope: string
      icons: Array<{ src: string; sizes: string; purpose?: string }>
    }

    expect(manifest).toMatchObject({
      name: 'Me&You',
      short_name: 'Me&You',
      description: 'Learn · Connect · Grow',
      theme_color: '#0B6BFF',
      background_color: '#FFFFFF',
      display: 'standalone',
      start_url: '/',
      scope: '/',
    })
    expect(manifest.icons).toEqual(expect.arrayContaining([
      expect.objectContaining({ src: '/brand/icon-192.png', sizes: '192x192' }),
      expect.objectContaining({ src: '/brand/icon-512.png', sizes: '512x512' }),
      expect.objectContaining({ src: '/brand/maskable-512.png', purpose: 'maskable' }),
    ]))
    for (const icon of manifest.icons) {
      expect(existsSync(resolve(publicDirectory, icon.src.slice(1)))).toBe(true)
    }
    expect(existsSync(resolve(publicDirectory, 'offline.html'))).toBe(true)
  })

  it('does not intercept or cache API requests in its fetch handler', () => {
    type WorkerFetchEvent = {
      request: {
        method: string
        url: string
        headers: { has: (name: string) => boolean }
        credentials: string
      }
      respondWith: (response: unknown) => void
    }
    const listeners: Record<string, (event: WorkerFetchEvent) => void> = {}
    const serviceWorker = readFileSync(resolve(publicDirectory, 'service-worker.js'), 'utf8')
    const self = {
      location: { origin: 'https://me-you.example' },
      addEventListener: (type: string, callback: (event: WorkerFetchEvent) => void) => {
        listeners[type] = callback
      },
    }
    runInNewContext(serviceWorker, { self, URL })

    const respondWith = vi.fn()
    listeners.fetch?.({
      request: {
        method: 'GET',
        url: 'https://me-you.example/api/v1/profile/me',
        headers: { has: vi.fn(() => false) },
        credentials: 'same-origin',
      },
      respondWith: () => respondWith(),
    })

    expect(respondWith).not.toHaveBeenCalled()
  })
})

describe('service worker registration', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('never registers in development', () => {
    const register = vi.fn()
    vi.stubGlobal('navigator', { serviceWorker: { register } })

    registerServiceWorker(false)

    expect(register).not.toHaveBeenCalled()
  })

  it('registers the worker in production', () => {
    const register = vi.fn().mockResolvedValue({})
    vi.stubGlobal('navigator', { serviceWorker: { register } })

    registerServiceWorker(true)

    expect(register).toHaveBeenCalledWith('/service-worker.js')
  })
})
