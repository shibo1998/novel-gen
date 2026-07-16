import type { ReactNode } from 'react'

interface AuthShellProps {
  title: string
  subtitle: string
  children: ReactNode
}

/**
 * Split-screen auth layout: an ink brand panel with a literary flourish on the
 * left, the form on the right. On mobile the brand panel collapses to a slim
 * header so the form stays front-and-center.
 */
export function AuthShell({ title, subtitle, children }: AuthShellProps) {
  return (
    <div className="relative z-10 flex min-h-screen flex-col lg:flex-row">
      {/* ── brand panel ── */}
      <div className="relative flex shrink-0 flex-col justify-between overflow-hidden border-b border-ink-700/60 bg-ink-900/50 px-8 py-8 lg:w-[44%] lg:border-b-0 lg:border-r lg:px-12 lg:py-14">
        {/* oversized watermark character */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -right-10 top-1/2 hidden -translate-y-1/2 select-none font-display text-[22rem] leading-none text-cinnabar-500/[0.06] lg:block"
        >
          墨
        </span>

        <div className="flex items-center gap-3">
          <span className="seal-mark h-10 w-10 text-xl leading-none">墨</span>
          <div>
            <div className="font-display text-lg font-semibold text-paper-50">墨韵</div>
            <div className="text-[11px] tracking-wide text-paper-300/40">AI 小说工坊</div>
          </div>
        </div>

        <div className="relative hidden lg:block">
          <p className="font-serif text-2xl leading-relaxed text-paper-100">
            一字一句，
            <br />
            皆由你落笔定夺。
          </p>
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-paper-300/45">
            从核心创意到世界观、大纲，再到逐章成稿——多智能体协同，你只需把握方向。
          </p>
        </div>

        <div className="hidden text-[11px] text-paper-300/30 lg:block">
          墨韵 · 让长篇创作有迹可循
        </div>
      </div>

      {/* ── form panel ── */}
      <div className="flex flex-1 items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-sm animate-fade-up">
          <h1 className="font-display text-3xl font-semibold text-paper-50">{title}</h1>
          <p className="mt-1.5 text-sm text-paper-300/50">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </div>
      </div>
    </div>
  )
}
