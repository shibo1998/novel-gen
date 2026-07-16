import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ErrorBoundary } from './components/ErrorBoundary'
import { CommandPalette } from './components/CommandPalette'
import { Toaster } from './components/Toaster'
import { OfflineIndicator } from './components/OfflineIndicator'
import { useAuthStore } from './stores/authStore'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import ProjectPage from './pages/ProjectPage'
import WritingSessionPage from './pages/WritingSessionPage'
import ProjectWorkbenchPage from './pages/ProjectWorkbenchPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function App() {
  const checkAuth = useAuthStore((state) => state.checkAuth)
  useEffect(() => { void checkAuth() }, [checkAuth])
  return (
    <ErrorBoundary><BrowserRouter>
      <CommandPalette />
      <Toaster />
      <OfflineIndicator />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/project/:projectId"
          element={
            <ProtectedRoute>
              <ProjectPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/project/:projectId/workbench"
          element={
            <ProtectedRoute>
              <ProjectWorkbenchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/project/:projectId/write/:chapterId"
          element={
            <ProtectedRoute>
              <WritingSessionPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter></ErrorBoundary>
  )
}

export default App
