const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const tokenStorage = {
  get: () => localStorage.getItem('access_token'),
  set: (token: string) => localStorage.setItem('access_token', token),
  clear: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
  },
}

export const getApiBaseUrl = () => API_BASE_URL

export const authHeaders = (): Record<string, string> => {
  const token = tokenStorage.get()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export const authorizedFetch = (path: string, init: RequestInit = {}) =>
  fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...authHeaders(),
      ...init.headers,
    },
  })

export const streamFetch = (path: string, init: RequestInit = {}) =>
  authorizedFetch(path, init)
