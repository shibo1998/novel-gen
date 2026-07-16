import { useCallback, useEffect, useState } from 'react'
import { Check, ExternalLink, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { workbenchApi } from '@/api/workbench'
import type { ContentVersion, ProjectChapter } from '@/types/workbench'

export function VersionsPanel({ projectId }: { projectId: string }) {
  const [chapters, setChapters] = useState<ProjectChapter[]>([])
  const [chapterId, setChapterId] = useState('')
  const [versions, setVersions] = useState<ContentVersion[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadChapters = useCallback(async () => {
    try {
      const result = await workbenchApi.listChapters(projectId)
      setChapters(result)
      setChapterId((current) => current || result.find((item) => item.active_content_version_id)?.id || result[0]?.id || '')
    } catch { setError('无法读取章节列表') }
  }, [projectId])
  const loadVersions = useCallback(async () => {
    if (!chapterId) { setVersions([]); return }
    try { setVersions(await workbenchApi.listContentVersions(chapterId)); setError(null) }
    catch { setError('无法读取正文版本') }
  }, [chapterId])
  useEffect(() => { void loadChapters() }, [loadChapters])
  useEffect(() => { void loadVersions() }, [loadVersions])

  const activate = async (version: ContentVersion) => {
    setBusy(true)
    try { await workbenchApi.activateContentVersion(chapterId, version.id); await loadVersions() }
    catch { setError('版本激活失败') }
    finally { setBusy(false) }
  }

  return (
    <section aria-labelledby="versions-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 id="versions-heading" className="text-base font-semibold text-paper-50">正文版本</h2><p className="mt-1 text-sm text-paper-300/45">AI、恢复与人工编辑都保留不可变版本。</p></div><div className="flex items-end gap-2"><label className="field-label min-w-52">章节<select className="field-input" value={chapterId} onChange={(event) => setChapterId(event.target.value)}>{chapters.map((chapter) => <option key={chapter.id} value={chapter.id}>第{chapter.chapter_number}章 {chapter.title || ''}</option>)}</select></label><button type="button" onClick={() => void loadVersions()} className="icon-button" title="刷新版本"><RefreshCw size={16} /><span className="sr-only">刷新</span></button></div></div>
      {error && <p role="alert" className="alert-error">{error}</p>}
      {!chapterId ? <p className="empty-state">尚无已规划章节</p> : versions.length === 0 ? <p className="empty-state">本章尚无正文版本</p> : <div className="table-shell"><table className="data-table"><thead><tr><th>版本</th><th>来源</th><th>说明</th><th>时间</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{versions.map((version) => <tr key={version.id}><td><span className="font-semibold text-paper-100">v{version.version_number}</span>{version.is_active && <span className="ml-2 status-chip status-completed">活动</span>}</td><td className="text-paper-200/70">{version.source}</td><td className="text-paper-300/45">{version.change_summary || '无说明'}</td><td className="text-paper-300/45">{new Date(version.created_at).toLocaleString()}</td><td className="text-right">{version.is_active ? <Check className="ml-auto text-jade-400" size={17} /> : <button type="button" disabled={busy} onClick={() => void activate(version)} className="action-button">激活</button>}</td></tr>)}</tbody></table></div>}
      {chapterId && <Link to={`/project/${projectId}/write/${chapterId}`} className="inline-flex items-center gap-2 text-sm text-cinnabar-300 transition hover:text-cinnabar-200">打开章节写作 <ExternalLink size={14} /></Link>}
    </section>
  )
}
