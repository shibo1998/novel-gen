import { FormEvent, useCallback, useEffect, useState } from 'react'
import { Check, RefreshCw } from 'lucide-react'
import { workbenchApi } from '@/api/workbench'
import type { StyleVersion } from '@/types/workbench'

export function StylePanel({ projectId }: { projectId: string }) {
  const [versions, setVersions] = useState<StyleVersion[]>([])
  const [sample, setSample] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try { setVersions(await workbenchApi.listStyleVersions(projectId)); setError(null) }
    catch { setError('无法读取风格版本') }
  }, [projectId])
  useEffect(() => { void load() }, [load])

  const create = async (event: FormEvent) => {
    event.preventDefault()
    if (sample.trim().length < 100) return
    setBusy(true)
    try { await workbenchApi.createStyleVersion(projectId, sample.trim()); setSample(''); await load() }
    catch { setError('风格分析失败') }
    finally { setBusy(false) }
  }
  const activate = async (version: StyleVersion) => {
    setBusy(true)
    try { await workbenchApi.activateStyleVersion(projectId, version.id); await load() }
    catch { setError('风格版本激活失败') }
    finally { setBusy(false) }
  }

  return (
    <section aria-labelledby="style-heading" className="space-y-5">
      <div className="flex items-center justify-between"><div><h2 id="style-heading" className="text-base font-semibold text-paper-50">项目风格版本</h2><p className="mt-1 text-sm text-paper-300/45">新写作任务读取活动版本，已启动任务继续使用冻结版本。</p></div><button type="button" onClick={() => void load()} className="icon-button" title="刷新风格"><RefreshCw size={16} /><span className="sr-only">刷新</span></button></div>
      <form onSubmit={(event) => void create(event)} className="border-y border-ink-700 py-4"><label className="field-label">风格样本（至少 100 字）<textarea className="field-textarea mt-1 min-h-28" value={sample} onChange={(event) => setSample(event.target.value)} placeholder="粘贴一段目标风格正文" /></label><div className="mt-2 flex items-center justify-between"><span className={`text-xs ${sample.trim().length >= 100 ? 'text-jade-400' : 'text-paper-300/40'}`}>{sample.trim().length}/100</span><button type="submit" disabled={sample.trim().length < 100 || busy} className="primary-button">分析并保存</button></div></form>
      {error && <p role="alert" className="alert-error">{error}</p>}
      {versions.length === 0 ? <p className="empty-state">尚无项目风格版本</p> : <div className="space-y-4">{versions.map((version) => <article key={version.id} className="border-b border-ink-700 pb-4"><div className="flex items-center justify-between gap-3"><div><span className="font-semibold text-paper-100">v{version.version_number}</span>{version.active && <span className="ml-2 status-chip status-completed">活动</span>}</div>{version.active ? <Check size={17} className="text-jade-400" /> : <button type="button" disabled={busy} onClick={() => void activate(version)} className="action-button">激活</button>}</div><pre className="result-block mt-3 max-h-48 overflow-auto">{JSON.stringify(version.profile, null, 2)}</pre></article>)}</div>}
    </section>
  )
}
