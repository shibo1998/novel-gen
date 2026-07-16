import { Sparkles } from 'lucide-react'
import type { WorldbuildingResult } from '@/types/api'

interface Props {
  value: WorldbuildingResult | null
  generating: boolean
  streamingText: string
  error: string | null
  onGenerate: () => void
  onDismissError: () => void
}

export function WorldbuildingTab({ value, generating, streamingText, error, onGenerate, onDismissError }: Props) {
  return (
    <div className="ink-card p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold text-paper-50">世界观设定</h2>
        <button type="button" onClick={onGenerate} disabled={generating} className="primary-button">
          {generating ? '生成中…' : (value ? '重新生成' : '生成世界观')}
        </button>
      </div>

      {generating && (
        <div className="mb-4 space-y-2">
          <div className="flex items-center gap-3 text-paper-200/60">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-cinnabar-500 border-t-transparent" />
            <span>AI 正在实时构建世界观…</span>
          </div>
          {streamingText && (
            <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-ink-700 bg-ink-950/70 p-4 font-serif text-sm leading-7 text-paper-200/80">
              {streamingText}
              <span className="ml-0.5 inline-block h-4 w-1.5 animate-ink-pulse bg-cinnabar-400 align-middle" />
            </pre>
          )}
        </div>
      )}

      {error && (
        <div className="alert-error mb-4">
          <span className="flex-1">生成失败：{error}</span>
          <button type="button" onClick={onDismissError} className="text-xs underline">关闭</button>
        </div>
      )}

      {value && !generating && (
        <div className="space-y-6">
          <section>
            <h3 className="section-label">世界设定</h3>
            <pre className="whitespace-pre-wrap rounded-md border border-ink-700 bg-ink-950/60 p-4 font-serif text-sm leading-7 text-paper-200/80">{value.setting_document}</pre>
          </section>
          <section>
            <h3 className="section-label">世界规则（不可违反）</h3>
            <ul className="space-y-1.5">
              {value.constraints.hard.map((rule, i) => (
                <li key={i} className="flex gap-2 text-sm text-paper-200/80">
                  <span className="mt-0.5 text-cinnabar-400">◆</span>
                  <span>{rule}</span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="section-label">风格约束</h3>
            <ul className="space-y-1.5">
              {value.constraints.soft.map((rule, i) => (
                <li key={i} className="flex gap-2 text-sm text-paper-300/60">
                  <span className="mt-0.5 text-paper-300/30">◇</span>
                  <span>{rule}</span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="section-label">核心冲突</h3>
            <div className="grid gap-3">
              {value.conflict_seeds.map((seed, i) => (
                <div key={i} className="ink-panel p-4">
                  <div className="font-serif font-semibold text-paper-50">{seed.name}</div>
                  <div className="mt-1 text-sm text-paper-200/60">{seed.description}</div>
                  <div className="mt-2 text-xs text-gold-300">利害关系：{seed.stake}</div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {!value && !generating && (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <Sparkles size={22} className="text-gold-400" />
          <p className="text-sm text-paper-300/45">点击上方按钮生成世界观</p>
        </div>
      )}
    </div>
  )
}
