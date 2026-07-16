import type { DhoDiff } from '@/types/workbench'

export function DhoDiffView({ diff }: { diff: DhoDiff }) {
  const empty = !diff.chapters_added.length && !diff.chapters_removed.length && !diff.chapters_modified.length
  if (empty) return <p className="text-sm text-paper-300/40">候选大纲没有章节级变化。</p>
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <div className="diff-column"><h4 className="diff-title text-jade-400">新增 {diff.chapters_added.length}</h4>{diff.chapters_added.map((chapter) => <p key={chapter.number} className="diff-line">第{chapter.number}章 {String(chapter.title || '')}</p>)}</div>
      <div className="diff-column"><h4 className="diff-title text-cinnabar-300">移除 {diff.chapters_removed.length}</h4>{diff.chapters_removed.map((chapter) => <p key={chapter.number} className="diff-line">第{chapter.number}章 {String(chapter.title || '')}</p>)}</div>
      <div className="diff-column"><h4 className="diff-title text-gold-300">修改 {diff.chapters_modified.length}</h4>{diff.chapters_modified.map((chapter) => <div key={chapter.number} className="diff-line"><p>第{chapter.number}章</p><p className="text-cinnabar-300/80">- {String(chapter.old.title || '')}</p><p className="text-jade-400/80">+ {String(chapter.new.title || '')}</p></div>)}</div>
    </div>
  )
}
