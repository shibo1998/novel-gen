import { useCallback, useEffect, useState } from 'react'
import { Check, RefreshCw } from 'lucide-react'
import { workbenchApi } from '@/api/workbench'
import type { ReviewItem } from '@/types/workbench'

export function ReviewsPanel({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<ReviewItem[]>([])
  const [loading, setLoading] = useState(true)
  const [resolving, setResolving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try { setItems(await workbenchApi.listReviews(projectId)) }
    catch { setError('无法读取人工审核队列') }
    finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { void load() }, [load])

  const resolve = async (item: ReviewItem) => {
    setResolving(item.id)
    setError(null)
    try {
      await workbenchApi.resolveReview(item.id, { outcome: 'reviewed', note: '人工审核完成' })
      setItems((current) => current.filter((candidate) => candidate.id !== item.id))
    } catch { setError('审核项处理失败') }
    finally { setResolving(null) }
  }

  return (
    <section aria-labelledby="reviews-heading" className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h2 id="reviews-heading" className="text-base font-semibold text-paper-50">人工审核队列</h2><p className="mt-1 text-sm text-paper-300/45">质量低分或评估不可用的章节会进入这里。</p></div>
        <button type="button" onClick={() => void load()} className="icon-button" title="刷新审核队列"><RefreshCw size={16} /><span className="sr-only">刷新</span></button>
      </div>
      {error && <p role="alert" className="alert-error">{error}</p>}
      {loading ? <p className="empty-state">正在读取审核项...</p> : items.length === 0 ? <p className="empty-state">当前没有待处理审核</p> : (
        <div className="divide-y divide-ink-700 border-y border-ink-700">
          {items.map((item) => (
            <article key={item.id} className="grid gap-4 py-4 md:grid-cols-[1fr_auto] md:items-center">
              <div>
                <div className="flex flex-wrap items-center gap-2"><span className="status-chip status-open">{item.priority}</span><span className="text-sm font-medium text-paper-100">{item.reason.verdict || item.type}</span></div>
                <p className="mt-2 text-sm text-paper-300/45">评估状态：{item.reason.evaluation_status || 'completed'}</p>
                {item.reason.weak_spots?.length ? <p className="mt-1 text-sm text-gold-300">短板：{item.reason.weak_spots.map((spot) => spot.label || '未命名').join('、')}</p> : null}
              </div>
              <button type="button" disabled={resolving !== null} onClick={() => void resolve(item)} className="action-button"><Check size={15} />{resolving === item.id ? '处理中' : '标记已处理'}</button>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
