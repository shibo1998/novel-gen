import { render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import App from './App'
import { useAuthStore } from './stores/authStore'

describe('authentication routing', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({
      isAuthenticated: false,
      user: null,
      isLoading: false,
      error: null,
    })
  })

  it('redirects an unauthenticated unknown route to login', async () => {
    window.history.pushState({}, '', '/unknown-route')

    render(<App />)

    await waitFor(() => expect(window.location.pathname).toBe('/login'))
  })
})
