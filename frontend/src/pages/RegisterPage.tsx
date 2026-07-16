import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/uiStore'
import { AuthShell } from '@/components/AuthShell'

export default function RegisterPage() {
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const { register, isLoading, error } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLocalError(null)
    if (password !== confirmPassword) {
      setLocalError('两次输入的密码不一致')
      return
    }
    try {
      await register({ email, password, username })
      toast.success('注册成功', '现在用新账号登录吧')
      navigate('/login')
    } catch {
      // error surfaced via store
    }
  }

  return (
    <AuthShell title="落笔" subtitle="创建账号，开启你的第一部长篇">
      {(localError || error) && <p className="alert-error mb-4">{localError || error}</p>}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="field-label" htmlFor="reg-email">邮箱</label>
          <input
            id="reg-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field-input"
            required
          />
        </div>
        <div>
          <label className="field-label" htmlFor="reg-username">用户名</label>
          <input
            id="reg-username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="field-input"
            required
            minLength={2}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="reg-password">密码</label>
          <input
            id="reg-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field-input"
            required
            minLength={6}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="reg-confirm">确认密码</label>
          <input
            id="reg-confirm"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="field-input"
            required
            minLength={6}
          />
        </div>
        <button type="submit" disabled={isLoading} className="primary-button w-full">
          {isLoading ? '注册中…' : '注册'}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-paper-300/50">
        已有账号?{' '}
        <Link to="/login" className="font-medium text-cinnabar-300 transition hover:text-cinnabar-200">
          去登录
        </Link>
      </p>
    </AuthShell>
  )
}
