import { apiClient } from './client'

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  username: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
}

export const authApi = {
  login: async (data: LoginRequest): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>('/api/auth/login', data)
    return response.data
  },

  register: async (data: RegisterRequest): Promise<void> => {
    await apiClient.post('/api/auth/register', data)
  },

  getCurrentUser: async (): Promise<{ id: string; email: string; username: string }> => {
    const response = await apiClient.get('/api/auth/me')
    return response.data
  },
}
