import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.resetModules()
  vi.unstubAllEnvs()
})

describe('Vite development server', () => {
  it('allows Codespaces hosts and uses the forwarded HTTPS HMR port', async () => {
    vi.stubEnv('CODESPACES', 'true')
    const { default: config } = await import('../../vite.config')

    expect(config.server?.host).toBe(true)
    expect(config.server?.allowedHosts).toContain('.app.github.dev')
    expect(config.server?.hmr).toEqual({ clientPort: 443 })
  })

  it('keeps the default HMR settings outside Codespaces', async () => {
    vi.stubEnv('CODESPACES', 'false')
    const { default: config } = await import('../../vite.config')

    expect(config.server?.hmr).toBeUndefined()
  })
})