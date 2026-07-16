import { useCallback, useEffect, useMemo, useState } from 'react'
import { Pause, Play, RotateCcw, Save } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { projectsApi } from '@/api/projects'
import { workbenchApi } from '@/api/workbench'
import { AppShell } from '@/components/AppShell'
import { OfflineEditor } from '@/components/OfflineEditor'
import { StreamingText } from '@/components/StreamingText'
import { useStreamingWrite } from '@/hooks/useStreamingWrite'
import { usePollTask } from '@/hooks/usePollTask'
import { useGenerationStore } from '@/stores/generationStore'
import { toast } from '@/stores/uiStore'
import type { TaskStatus } from '@/types/api'
import type { ProjectChapter, SceneSummary } from '@/types/workbench'

interface OutlineDetails {
  goal: string
  keyEvents: Array<{ event_name: string; brief: string }>
}

interface TaskWarning {
  code: string
  message: string
  foreshadowing_id?: string
}

const taskWarnings = (status: TaskStatus): TaskWarning[] => {
  const result = status.result as { warnings?: TaskWarning[] } | null | undefined
  return Array.isArray(result?.warnings) ? result.warnings : []
}

export default function WritingSessionPage() {
  const { projectId, chapterId: chapterParam } = useParams<{ projectId: string; chapterId: string }>()
  const [projectTitle, setProjectTitle] = useState<string>('')
  const [chapter, setChapter] = useState<ProjectChapter | null>(null)
  const [scenes, setScenes] = useState<SceneSummary[]>([])
  const [sceneId, setSceneId] = useState('')
  const [outline, setOutline] = useState<OutlineDetails>({ goal: '', keyEvents: [] })
  const [isLoading, setIsLoading] = useState(true)
  const [isExpanding, setIsExpanding] = useState(false)
  const [viewMode, setViewMode] = useState<'stream' | 'edit'>('stream')
  const [pageError, setPageError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<TaskWarning[]>([])
  const pollTask = usePollTask()
  const resetGeneration = useGenerationStore((state) => state.reset)
  const activeScene = useMemo(() => scenes.find((scene) => scene.id === sceneId) || null, [sceneId, scenes])

  const { isStreaming, isRecovering, content, error, startWriting, stopWriting } = useStreamingWrite({
    sceneId,
    onDone: () => setViewMode('stream'),
    onError: (reason) => setPageError(reason.message),
  })

  const loadData = useCallback(async () => {
    if (!projectId || !chapterParam) return
    setIsLoading(true)
    setPageError(null)
    try {
      projectsApi.get(projectId).then((p) => setProjectTitle(p.title)).catch(() => undefined)
      const chapters = await workbenchApi.listChapters(projectId)
      const current = chapters.find(
        (item) => item.id === chapterParam || String(item.chapter_number) === chapterParam,
      )
      if (!current) throw new Error('章节不存在')
      setChapter(current)
      const sceneRows = await workbenchApi.listScenes(projectId, current.id)
      setScenes(sceneRows)
      setSceneId((selected) => sceneRows.some((scene) => scene.id === selected) ? selected : sceneRows[0]?.id || '')
      try {
        const outlineResult = await projectsApi.getOutline(projectId)
        const details = outlineResult.chapters.find((item) => item.number === current.chapter_number)
        setOutline({ goal: details?.goal || '', keyEvents: details?.key_events || [] })
      } catch { setOutline({ goal: '', keyEvents: [] }) }
    } catch (reason) {
      setPageError(reason instanceof Error ? reason.message : '章节加载失败')
    } finally {
      setIsLoading(false)
    }
  }, [chapterParam, projectId])

  useEffect(() => { void loadData() }, [loadData])
  useEffect(() => { resetGeneration() }, [resetGeneration, sceneId])

  const expand = async () => {
    if (!projectId || !chapter) return
    setIsExpanding(true)
    setPageError(null)
    setWarnings([])
    try {
      const task = await workbenchApi.expandChapter(projectId, chapter.id)
      if (task.status === 'completed' || !task.task_id) {
        await loadData()
        setIsExpanding(false)
        return
      }
      pollTask(task.task_id, {
        intervalMs: 1000,
        onComplete: async (status) => {
          setWarnings(taskWarnings(status))
          await loadData()
          setIsExpanding(false)
        },
        onFailed: (status) => {
          setPageError(status.error || '场景展开任务失败')
          setIsExpanding(false)
        },
      })
    } catch (reason) {
      setPageError(reason instanceof Error ? reason.message : '场景展开失败')
      setIsExpanding(false)
    }
  }

  const save = async (newContent: string) => {
    if (!sceneId) return
    try {
      await workbenchApi.saveScene(sceneId, newContent)
      setScenes((items) => items.map((scene) => scene.id === sceneId ? {
        ...scene,
        content: newContent,
        word_count: newContent.length,
        status: 'draft',
      } : scene))
      setPageError(null)
      toast.success('正文已保存')
    } catch {
      setPageError('正文保存失败')
      toast.error('正文保存失败')
    }
  }

  const chapterTitle = chapter ? `第${chapter.chapter_number}章 · ${chapter.title || '未命名'}` : '写作'

  return (
    <AppShell
      active="write"
      projectId={projectId}
      projectTitle={projectTitle}
      headerRight={
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setViewMode('stream')} className={viewMode === 'stream' ? 'action-button' : 'secondary-button'}>生成</button>
          <button type="button" onClick={() => setViewMode('edit')} className={viewMode === 'edit' ? 'action-button' : 'secondary-button'}>编辑</button>
        </div>
      }
    >
      {isLoading ? (
        <div className="flex items-center justify-center py-24 text-sm text-paper-300/40">
          <span className="mr-3 h-4 w-4 animate-spin rounded-full border-2 border-cinnabar-500 border-t-transparent" />
          加载中…
        </div>
      ) : (
        <div className="mx-auto max-w-4xl space-y-5">
          <div>
            <h1 className="font-display text-2xl font-semibold text-paper-50">{chapterTitle}</h1>
          </div>

          {pageError && <p role="alert" className="alert-error">{pageError}</p>}

          {warnings.length > 0 && (
            <section role="status" className="rounded-lg border border-gold-500/40 bg-gold-500/10 p-3 text-sm text-gold-300">
              <h2 className="font-medium">场景计划警告</h2>
              <ul className="mt-2 space-y-1">
                {warnings.map((warning, index) => (
                  <li key={`${warning.code}-${warning.foreshadowing_id || index}`}>{warning.message}</li>
                ))}
              </ul>
            </section>
          )}

          {(outline.goal || outline.keyEvents.length > 0) && (
            <div className="ink-panel grid gap-4 p-4 sm:grid-cols-2">
              {outline.goal && (
                <section>
                  <h2 className="section-label">本章目标</h2>
                  <p className="text-sm leading-relaxed text-paper-200/80">{outline.goal}</p>
                </section>
              )}
              {outline.keyEvents.length > 0 && (
                <section>
                  <h2 className="section-label">关键事件</h2>
                  <ol className="plain-list">
                    {outline.keyEvents.map((event, index) => (
                      <li key={`${event.event_name}-${index}`}>{index + 1}. {event.event_name}：{event.brief}</li>
                    ))}
                  </ol>
                </section>
              )}
            </div>
          )}

          {scenes.length === 0 ? (
            <section className="empty-state">
              <p className="text-paper-300/50">本章还没有场景约束卡。</p>
              <button type="button" onClick={() => void expand()} disabled={isExpanding} className="primary-button mx-auto mt-4">
                {isExpanding ? '正在展开…' : '生成场景计划'}
              </button>
            </section>
          ) : (
            <>
              <div className="flex flex-wrap gap-2" role="tablist" aria-label="章节场景">
                {scenes.map((scene) => (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={scene.id === sceneId}
                    key={scene.id}
                    onClick={() => setSceneId(scene.id)}
                    className={scene.id === sceneId ? 'action-button' : 'secondary-button'}
                  >
                    场景 {scene.scene_number}
                  </button>
                ))}
              </div>

              <section className="ink-card overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-700/70 bg-ink-900/40 p-4">
                  <div>
                    <h2 className="font-serif text-base font-medium text-paper-50">{activeScene?.title || `场景 ${activeScene?.scene_number}`}</h2>
                    <p className="mt-1 text-xs text-paper-300/45">
                      {isRecovering ? '正在重新生成整个场景，旧缓冲已清空' : isStreaming ? '正在接收正文…' : content ? `${content.length} 字符` : activeScene?.status || '准备就绪'}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    {isStreaming ? (
                      <button type="button" onClick={stopWriting} className="secondary-button"><Pause size={15} />停止</button>
                    ) : (
                      <button type="button" onClick={() => void startWriting(content ? content.length : 0)} className="action-button">
                        {content ? <RotateCcw size={15} /> : <Play size={15} />}{content ? '整场景重写' : '开始写作'}
                      </button>
                    )}
                    {content && !isStreaming && (
                      <button type="button" onClick={() => setViewMode('edit')} className="secondary-button"><Save size={15} />编辑保存</button>
                    )}
                  </div>
                </div>
                <div className="min-h-[28rem] p-5 sm:p-7">
                  {viewMode === 'stream'
                    ? <div className="manuscript"><StreamingText content={content || activeScene?.content || ''} /></div>
                    : <OfflineEditor initialContent={content || activeScene?.content || ''} onSave={(value) => void save(value)} />}
                </div>
                {error && <div className="border-t border-cinnabar-700/50 bg-cinnabar-700/15 p-3 text-sm text-cinnabar-300">{error.message}</div>}
              </section>
            </>
          )}
        </div>
      )}
    </AppShell>
  )
}
