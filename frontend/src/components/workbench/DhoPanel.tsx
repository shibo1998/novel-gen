import { FormEvent, useCallback, useEffect, useState } from 'react'
import { Check, RefreshCw, X } from 'lucide-react'
import { workbenchApi } from '@/api/workbench'
import type { DhoCandidate } from '@/types/workbench'
import { DhoDiffView } from './DhoDiffView'

export function DhoPanel({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<DhoCandidate[]>([])
  const [trigger, setTrigger] = useState('')
  const [affectedFrom, setAffectedFrom] = useState(1)
  const [busy, setBusy] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    setLoading(true)
    try { setItems(await workbenchApi.listDhoCandidates(projectId)); setError(null) }
    catch { setError('无法读取重规划候选') }
    finally { setLoading(false) }
  }, [projectId])
  useEffect(() => { void load() }, [load])

  const create = async (event: FormEvent) => {
    event.preventDefault()
    if (!trigger.trim()) return
    setBusy('create')
    try {
      await workbenchApi.createDhoCandidate(projectId, {
        affected_from: affectedFrom,
        trigger: { type: 'manual_deviation', description: trigger.trim() },
      })
      setTrigger('')
      await load()
    } catch { setError('生成候选失败，请确认已有正式大纲且 LLM 可用') }
    finally { setBusy(null) }
  }

  const decide = async (candidate: DhoCandidate, action: 'approve' | 'reject') => {
    setBusy(candidate.id)
    try { await workbenchApi.decideDhoCandidate(projectId, candidate.id, action); await load() }
    catch { setError(action === 'approve' ? '批准失败，活动大纲可能已变化' : '拒绝失败') }
    finally { setBusy(null) }
  }

  return (
    <section aria-labelledby="dho-heading" className="space-y-5">
      <div className="flex items-center justify-between"><div><h2 id="dho-heading" className="text-base font-semibold text-paper-50">动态大纲重规划</h2><p className="mt-1 text-sm text-paper-300/45">候选只修改受影响边界之后的未写章节。</p></div><button type="button" onClick={() => void load()} className="icon-button" title="刷新候选"><RefreshCw size={16} /><span className="sr-only">刷新</span></button></div>
      <form onSubmit={(event) => void create(event)} className="grid gap-3 border-y border-ink-700 py-4 md:grid-cols-[9rem_1fr_auto] md:items-end">
        <label className="field-label">起始章节<input className="field-input" type="number" min={1} value={affectedFrom} onChange={(event) => setAffectedFrom(Number(event.target.value))} /></label>
        <label className="field-label">偏离或变更原因<input className="field-input" value={trigger} onChange={(event) => setTrigger(event.target.value)} placeholder="例如：第30章角色选择背叛" /></label>
        <button type="submit" disabled={!trigger.trim() || busy !== null} className="primary-button">{busy === 'create' ? '生成中' : '生成候选'}</button>
      </form>
      {error && <p role="alert" className="alert-error">{error}</p>}
      {loading ? <p className="empty-state">正在读取候选...</p> : items.length === 0 ? <p className="empty-state">暂无重规划候选</p> : items.map((candidate) => (
        <article key={candidate.id} className="border-b border-ink-700 pb-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3"><div><span className={`status-chip status-${candidate.status}`}>{candidate.status}</span><span className="ml-2 text-sm text-paper-200/70">从第 {candidate.affected_from} 章开始</span></div>{candidate.status === 'pending_review' && <div className="flex gap-2"><button type="button" disabled={busy !== null} onClick={() => void decide(candidate, 'reject')} className="secondary-button"><X size={15} />拒绝</button><button type="button" disabled={busy !== null} onClick={() => void decide(candidate, 'approve')} className="action-button"><Check size={15} />批准</button></div>}</div>
          <DhoDiffView diff={candidate.diff} />
        </article>
      ))}
    </section>
  )
}
