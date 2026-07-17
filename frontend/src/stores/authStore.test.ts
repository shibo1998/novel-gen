import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authApi } from '@/api/auth'
import { tokenStorage } from '@/api/http'
import { useAuthStore } from './authStore'

vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    getCurrentUser: vi.fn(),
  },
}))

describe('authStore.checkAuth', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    useAuthStore.setState({
      isAuthenticated: false,
      user: null,
      isLoading: false,
      error: null,
    })
  })

  it('keeps the session when the backend is temporarily unavailable', async () => {
    tokenStorage.set('still-valid-token')
    useAuthStore.setState({
      isAuthenticated: true,
      user: { id: 'user-1', email: 'writer@example.com', username: 'writer' },
    })
    vi.mocked(authApi.getCurrentUser).mockRejectedValueOnce(new Error('Network Error'))

    await useAuthStore.getState().checkAuth()

    expect(tokenStorage.get()).toBe('still-valid-token')
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(useAuthStore.getState().user?.id).toBe('user-1')
  })

  it('clears stale user state when no token exists', async () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: { id: 'user-1', email: 'writer@example.com', username: 'writer' },
    })

    await useAuthStore.getState().checkAuth()

    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('clears the session after a definitive authentication failure', async () => {
    tokenStorage.set('expired-token')
    useAuthStore.setState({ isAuthenticated: true })
    vi.mocked(authApi.getCurrentUser).mockRejectedValueOnce({
      response: { status: 401 },
    })

    await useAuthStore.getState().checkAuth()

    expect(tokenStorage.get()).toBeNull()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(useAuthStore.getState().user).toBeNull()
  })
})
