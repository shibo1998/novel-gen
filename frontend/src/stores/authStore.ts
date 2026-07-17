import { create } from 'zustand'
import { authApi, LoginRequest, RegisterRequest } from '@/api/auth'
import { tokenStorage } from '@/api/http'

interface AuthState {
  isAuthenticated: boolean
  user: { id: string; email: string; username: string } | null
  isLoading: boolean
  error: string | null
  login: (credentials: LoginRequest) => Promise<void>
  register: (data: RegisterRequest) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: !!tokenStorage.get(),
  user: null,
  isLoading: false,
  error: null,

  login: async (credentials) => {
    set({ isLoading: true, error: null })
    try {
      const response = await authApi.login(credentials)
      tokenStorage.set(response.access_token)
      const user = await authApi.getCurrentUser()
      set({ isAuthenticated: true, user, isLoading: false })
    } catch (error: any) {
      set({
        error: error.response?.data?.detail || 'Login failed',
        isLoading: false,
      })
      throw error
    }
  },

  register: async (data) => {
    set({ isLoading: true, error: null })
    try {
      await authApi.register(data)
      set({ isLoading: false })
    } catch (error: any) {
      set({
        error: error.response?.data?.detail || 'Registration failed',
        isLoading: false,
      })
      throw error
    }
  },

  logout: () => {
    tokenStorage.clear()
    set({ isAuthenticated: false, user: null })
  },

  checkAuth: async () => {
    const token = tokenStorage.get()
    if (!token) {
      set({ isAuthenticated: false, user: null, isLoading: false })
      return
    }
    set({ isLoading: true })
    try {
      const user = await authApi.getCurrentUser()
      set({ isAuthenticated: true, user, isLoading: false })
    } catch (error: any) {
      console.error('Authentication check failed', error)
      const status = error.response?.status
      const authenticationFailed = status === 401 || status === 403 || status === 404
      if (authenticationFailed) {
        tokenStorage.clear()
        set({ isAuthenticated: false, user: null, isLoading: false })
        return
      }

      // Service restarts, timeouts and 5xx responses do not invalidate a JWT.
      set({ isAuthenticated: true, isLoading: false })
    }
  },
}))
