import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/uiStore'
import { AuthShell } from '@/components/AuthShell'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const { login, isLoading, error } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await login({ email, password })
      toast.success('欢迎回来')
      navigate('/')
    } catch {
      // error surfaced via store
    }
  }

  return (
    <AuthShell title="提笔" subtitle="登录以继续你的创作">
      {error && <p className="alert-error mb-4">{error}</p>}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="field-label" htmlFor="login-email">邮箱</label>
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field-input"
            required
          />
        </div>
        <div>
          <label className="field-label" htmlFor="login-password">密码</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field-input"
            required
          />
        </div>
        <button type="submit" disabled={isLoading} className="primary-button w-full">
          {isLoading ? '登录中…' : '登录'}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-paper-300/50">
        还没有账号?{' '}
        <Link to="/register" className="font-medium text-cinnabar-300 transition hover:text-cinnabar-200">
          注册一个
        </Link>
      </p>
    </AuthShell>
  )
}
