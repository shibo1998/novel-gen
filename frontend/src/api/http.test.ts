import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authorizedFetch, tokenStorage } from './http'

describe('authorizedFetch', () => {
  beforeEach(() => {
    localStorage.clear()
    window.history.pushState({}, '', '/login')
    vi.restoreAllMocks()
  })

  it('clears an invalid token after a 401 response', async () => {
    tokenStorage.set('invalid-token')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })))

    await authorizedFetch('/api/projects')

    expect(tokenStorage.get()).toBeNull()
  })
})
