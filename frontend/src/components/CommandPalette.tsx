import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BookOpen,
  CornerDownLeft,
  FileText,
  Home,
  LogOut,
  Plus,
  Search,
  Settings2,
  Sparkles,
} from 'lucide-react'
import { useUIStore } from '@/stores/uiStore'
import { useAuthStore } from '@/stores/authStore'
import { projectsApi, type Project } from '@/api/projects'

type Command = {
  id: string
  label: string
  hint?: string
  group: string
  icon: typeof Home
  keywords?: string
  run: () => void
}

export function CommandPalette() {
  const open = useUIStore((s) => s.paletteOpen)
  const setOpen = useUIStore((s) => s.setPaletteOpen)
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [projects, setProjects] = useState<Project[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Global ⌘K / Ctrl+K toggle
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        useUIStore.getState().togglePalette()
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setOpen])

  // Load projects lazily when opened
  useEffect(() => {
    if (open && isAuthenticated) {
      projectsApi.list().then(setProjects).catch(() => undefined)
      setQuery('')
      setActive(0)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open, isAuthenticated])

  const commands = useMemo<Command[]>(() => {
    const base: Command[] = [
      {
        id: 'nav-dashboard',
        label: '前往项目总览',
        group: '导航',
        icon: Home,
        keywords: 'dashboard home 首页 总览',
        run: () => navigate('/'),
      },
      {
        id: 'new-project',
        label: '新建项目',
        hint: '创建一部新小说',
        group: '操作',
        icon: Plus,
        keywords: 'new create 创建 新建',
        run: () => navigate('/?new=1'),
      },
      {
        id: 'logout',
        label: '退出登录',
        group: '账户',
        icon: LogOut,
        keywords: 'logout signout 退出 登出',
        run: () => {
          logout()
          navigate('/login')
        },
      },
    ]
    const projectCmds: Command[] = projects.flatMap((p) => [
      {
        id: `p-${p.id}`,
        label: p.title,
        hint: p.genre || '项目',
        group: '项目',
        icon: BookOpen,
        keywords: `${p.title} ${p.core_idea} ${p.genre ?? ''}`,
        run: () => navigate(`/project/${p.id}`),
      },
      {
        id: `pw-${p.id}`,
        label: `${p.title} · 生产控制台`,
        hint: '工作台',
        group: '项目',
        icon: Settings2,
        keywords: `${p.title} workbench 工作台 控制台`,
        run: () => navigate(`/project/${p.id}/workbench`),
      },
    ])
    return [...base, ...projectCmds]
  }, [projects, navigate, logout])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return commands
    return commands.filter((c) =>
      `${c.label} ${c.keywords ?? ''}`.toLowerCase().includes(q),
    )
  }, [commands, query])

  useEffect(() => {
    setActive((a) => Math.min(a, Math.max(0, filtered.length - 1)))
  }, [filtered.length])

  if (!open) return null

  const groups = filtered.reduce<Record<string, Command[]>>((acc, c) => {
    (acc[c.group] ??= []).push(c)
    return acc
  }, {})

  const runAt = (index: number) => {
    const cmd = filtered[index]
    if (!cmd) return
    setOpen(false)
    cmd.run()
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(a + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      runAt(active)
    }
  }

  let flatIndex = -1

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center bg-ink-950/70 px-4 pt-[12vh] backdrop-blur-sm animate-fade-in"
      onMouseDown={() => setOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="命令面板"
        className="w-full max-w-xl overflow-hidden rounded-xl border border-ink-700 bg-ink-800/95 shadow-lift animate-scale-in"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-ink-700 px-4">
          <Search size={18} className="shrink-0 text-cinnabar-400" aria-hidden="true" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setActive(0)
            }}
            onKeyDown={onKeyDown}
            placeholder="搜索项目、跳转、执行操作…"
            className="min-h-14 w-full bg-transparent text-base text-paper-50 outline-none placeholder:text-paper-300/30"
          />
          <kbd className="hidden shrink-0 rounded border border-ink-600 px-1.5 py-0.5 font-mono text-[10px] text-paper-300/40 sm:block">
            ESC
          </kbd>
        </div>

        <div ref={listRef} className="max-h-[52vh] overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-paper-300/40">
              <Sparkles size={20} className="text-gold-400" />
              没有匹配的结果
            </div>
          ) : (
            Object.entries(groups).map(([group, cmds]) => (
              <div key={group} className="mb-1">
                <div className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-paper-300/35">
                  {group}
                </div>
                {cmds.map((cmd) => {
                  flatIndex += 1
                  const idx = flatIndex
                  const Icon = cmd.icon
                  const isActive = idx === active
                  return (
                    <button
                      key={cmd.id}
                      type="button"
                      onMouseEnter={() => setActive(idx)}
                      onClick={() => runAt(idx)}
                      className={`flex w-full items-center gap-3 rounded-lg px-2.5 py-2.5 text-left transition ${
                        isActive
                          ? 'bg-cinnabar-500/15 text-paper-50'
                          : 'text-paper-200/70 hover:bg-ink-700/50'
                      }`}
                    >
                      <span
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md border ${
                          isActive
                            ? 'border-cinnabar-500/40 bg-cinnabar-500/15 text-cinnabar-300'
                            : 'border-ink-600 bg-ink-900/60 text-paper-200/50'
                        }`}
                      >
                        <Icon size={16} aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">{cmd.label}</span>
                        {cmd.hint && (
                          <span className="block truncate text-xs text-paper-300/40">{cmd.hint}</span>
                        )}
                      </span>
                      {isActive && (
                        <CornerDownLeft size={14} className="shrink-0 text-paper-300/40" aria-hidden="true" />
                      )}
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>

        <div className="flex items-center justify-between border-t border-ink-700 px-4 py-2 text-[11px] text-paper-300/35">
          <span className="flex items-center gap-1.5">
            <FileText size={12} /> {filtered.length} 项
          </span>
          <span className="flex items-center gap-3">
            <span>↑↓ 选择</span>
            <span>↵ 执行</span>
          </span>
        </div>
      </div>
    </div>
  )
}
