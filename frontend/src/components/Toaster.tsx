import { CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { useUIStore, type ToastKind } from '@/stores/uiStore'

const ICON: Record<ToastKind, typeof Info> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
}

const ACCENT: Record<ToastKind, string> = {
  success: 'border-l-jade-500 text-jade-400',
  error: 'border-l-cinnabar-500 text-cinnabar-300',
  info: 'border-l-gold-500 text-gold-300',
}

export function Toaster() {
  const toasts = useUIStore((s) => s.toasts)
  const dismiss = useUIStore((s) => s.dismissToast)

  if (toasts.length === 0) return null

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed bottom-5 right-5 z-[100] flex w-[min(92vw,22rem)] flex-col gap-2"
    >
      {toasts.map((t) => {
        const Icon = ICON[t.kind]
        return (
          <div
            key={t.id}
            role="status"
            className={`pointer-events-auto flex items-start gap-3 rounded-lg border border-ink-700 border-l-2 bg-ink-800/95 px-3.5 py-3 shadow-lift backdrop-blur-sm animate-toast-in ${ACCENT[t.kind]}`}
          >
            <Icon size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-paper-50">{t.message}</p>
              {t.detail && <p className="mt-0.5 text-xs text-paper-200/50">{t.detail}</p>}
            </div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              className="-mr-1 -mt-0.5 shrink-0 rounded p-1 text-paper-300/40 transition hover:bg-ink-700 hover:text-paper-100"
              aria-label="关闭通知"
            >
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
