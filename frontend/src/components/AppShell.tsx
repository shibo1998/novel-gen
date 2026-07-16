import { useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  BookMarked,
  Command,
  LayoutGrid,
  LogOut,
  Menu,
  PenLine,
  Search,
  Settings2,
  X,
} from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'

interface AppShellProps {
  children: ReactNode
  /** current project context, when inside a project */
  projectId?: string
  projectTitle?: string
  /** right-aligned header slot (status chips, contextual actions) */
  headerRight?: ReactNode
  /** which sidebar section is active */
  active?: 'dashboard' | 'project' | 'workbench' | 'write'
}

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

export function AppShell({ children, projectId, projectTitle, headerRight, active }: AppShellProps) {
  const { user, logout } = useAuthStore()
  const openPalette = useUIStore((s) => s.openPalette)
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  // close the mobile drawer whenever the route changes
  useEffect(() => setMobileOpen(false), [location.pathname])

  const nav: Array<{
    key: NonNullable<AppShellProps['active']>
    label: string
    hint: string
    icon: typeof LayoutGrid
    to: string
    show: boolean
  }> = [
    { key: 'dashboard', label: '项目总览', hint: '所有小说', icon: LayoutGrid, to: '/', show: true },
    {
      key: 'project',
      label: '创作设定',
      hint: '世界观 · 大纲',
      icon: BookMarked,
      to: projectId ? `/project/${projectId}` : '/',
      show: Boolean(projectId),
    },
    {
      key: 'workbench',
      label: '生产控制台',
      hint: '任务 · 审校 · 版本',
      icon: Settings2,
      to: projectId ? `/project/${projectId}/workbench` : '/',
      show: Boolean(projectId),
    },
  ]

  const SidebarContent = () => (
    <div className="flex h-full flex-col">
      {/* brand */}
      <Link to="/" className="flex items-center gap-3 px-5 py-5">
        <span className="seal-mark h-9 w-9 text-lg leading-none">墨</span>
        <span className="min-w-0">
          <span className="block font-display text-base font-semibold text-paper-50">墨韵</span>
          <span className="block text-[11px] tracking-wide text-paper-300/40">AI 小说工坊</span>
        </span>
      </Link>

      {projectTitle && (
        <div className="mx-3 mb-2 rounded-lg border border-ink-700/70 bg-ink-900/50 px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-cinnabar-400/70">
            <PenLine size={11} /> 当前项目
          </div>
          <div className="mt-1 truncate font-serif text-sm text-paper-100" title={projectTitle}>
            {projectTitle}
          </div>
        </div>
      )}

      <nav aria-label="主导航" className="flex-1 space-y-1 px-3 py-2">
        {nav
          .filter((item) => item.show)
          .map((item) => {
            const Icon = item.icon
            const on = active === item.key
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => navigate(item.to)}
                aria-current={on ? 'page' : undefined}
                className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition ${
                  on
                    ? 'bg-cinnabar-500/[0.12] text-cinnabar-200 shadow-[inset_2px_0_0_theme(colors.cinnabar.500)]'
                    : 'text-paper-200/60 hover:bg-ink-700/50 hover:text-paper-50'
                }`}
              >
                <Icon
                  size={17}
                  className={on ? 'text-cinnabar-300' : 'text-paper-300/40 group-hover:text-paper-200/70'}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{item.label}</span>
                  <span className="block truncate text-[11px] text-paper-300/35">{item.hint}</span>
                </span>
              </button>
            )
          })}
      </nav>

      {/* command palette hint */}
      <div className="px-3 pb-2">
        <button
          type="button"
          onClick={openPalette}
          className="flex w-full items-center gap-2.5 rounded-lg border border-ink-700 bg-ink-900/50 px-3 py-2.5 text-sm text-paper-300/50 transition hover:border-cinnabar-500/40 hover:text-paper-100"
        >
          <Search size={15} />
          <span className="flex-1 text-left">快速跳转</span>
          <kbd className="flex items-center gap-0.5 rounded border border-ink-600 px-1.5 py-0.5 font-mono text-[10px] text-paper-300/40">
            {isMac ? <Command size={9} /> : 'Ctrl'}K
          </kbd>
        </button>
      </div>

      {/* user */}
      <div className="border-t border-ink-700/60 p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-1.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cinnabar-500 to-cinnabar-700 font-display text-sm text-white">
            {(user?.username || '?').slice(0, 1).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm text-paper-100">{user?.username || '未登录'}</span>
            <span className="block truncate text-[11px] text-paper-300/35">{user?.email}</span>
          </span>
          <button
            type="button"
            onClick={() => {
              logout()
              navigate('/login')
            }}
            className="shrink-0 rounded-md p-1.5 text-paper-300/40 transition hover:bg-cinnabar-500/15 hover:text-cinnabar-300"
            title="退出登录"
          >
            <LogOut size={15} />
            <span className="sr-only">退出登录</span>
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen">
      <div className="relative z-10 mx-auto flex max-w-[1500px]">
        {/* ── desktop sidebar ── */}
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-ink-700/60 bg-ink-900/40 backdrop-blur-sm lg:block">
          <SidebarContent />
        </aside>

        {/* ── mobile drawer ── */}
        {mobileOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div className="absolute inset-0 bg-ink-950/70 backdrop-blur-sm animate-fade-in" onClick={() => setMobileOpen(false)} />
            <aside className="absolute left-0 top-0 h-full w-72 border-r border-ink-700 bg-ink-900 shadow-lift animate-scale-in">
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="absolute right-3 top-4 rounded-md p-1.5 text-paper-300/50 hover:bg-ink-700 hover:text-paper-50"
                aria-label="关闭菜单"
              >
                <X size={18} />
              </button>
              <SidebarContent />
            </aside>
          </div>
        )}

        {/* ── main column ── */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex min-h-14 items-center gap-3 border-b border-ink-700/60 bg-ink-950/80 px-4 backdrop-blur-md sm:px-6">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              className="icon-button lg:hidden"
              aria-label="打开菜单"
            >
              <Menu size={18} />
            </button>
            <div className="min-w-0 flex-1" />
            <button
              type="button"
              onClick={openPalette}
              className="hidden items-center gap-2 rounded-md border border-ink-600 bg-ink-800/60 px-2.5 py-1.5 text-xs text-paper-300/50 transition hover:border-cinnabar-500/40 hover:text-paper-100 sm:flex"
            >
              <Search size={13} />
              <span>搜索 / 命令</span>
              <kbd className="flex items-center gap-0.5 rounded border border-ink-600 px-1 font-mono text-[10px]">
                {isMac ? <Command size={8} /> : 'Ctrl'}K
              </kbd>
            </button>
            {headerRight}
          </header>

          <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
        </div>
      </div>
    </div>
  )
}
