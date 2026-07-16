import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { PenLine, Plus, Sparkles } from 'lucide-react'
import { projectsApi, Project } from '@/api/projects'
import type { WorldbuildingResult, OutlineResult, TaskStatus } from '@/types/api'
import { streamFetch } from '@/api/http'
import { usePollTask } from '@/hooks/usePollTask'
import { toast } from '@/stores/uiStore'
import { AppShell } from '@/components/AppShell'
import { WorldbuildingTab } from '@/components/project/WorldbuildingTab'

// SSE stream handler for worldbuilding generation
type StreamHandlers = {
  onToken: (chunk: string) => void
  onDone: (result: WorldbuildingResult) => void
  onError: (err: string) => void
}

// Subscribe to worldbuilding task's SSE stream
function openWorldbuildingStream(taskId: string, handlers: StreamHandlers): () => void {
  const controller = new AbortController()
  void (async () => {
    try {
      const response = await streamFetch(`/api/projects/worldbuilding/stream/${taskId}`, {
        signal: controller.signal,
      })
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() || ''
        for (const block of blocks) {
          const event = block.match(/^event:\s*(.+)$/m)?.[1]
          const raw = block.match(/^data:\s*(.+)$/m)?.[1]
          if (!raw) continue
          const data = JSON.parse(raw)
          if (event === 'token' && data.chunk) handlers.onToken(data.chunk)
          if (event === 'done') {
            handlers.onDone(data.result)
            controller.abort()
            return
          }
        }
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        console.error('Worldbuilding stream failed', error)
        handlers.onError('connection error')
      }
    }
  })()
  return () => controller.abort()
}

const VOL_STATUS: Record<string, { label: string; cls: string }> = {
  detailed: { label: '已规划完整', cls: 'border-cinnabar-500/40 bg-cinnabar-500/10 text-cinnabar-300' },
  planning: { label: '规划中', cls: 'border-gold-500/40 bg-gold-500/10 text-gold-300' },
  planned: { label: '待规划', cls: 'border-ink-600 bg-ink-800 text-paper-300/50' },
  completed: { label: '已完成', cls: 'border-jade-500/40 bg-jade-500/10 text-jade-400' },
  writing: { label: '写作中', cls: 'border-gold-500/40 bg-gold-500/10 text-gold-300' },
}

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [worldbuilding, setWorldbuilding] = useState<WorldbuildingResult | null>(null)
  const [outline, setOutline] = useState<OutlineResult | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isGeneratingWorldbuilding, setIsGeneratingWorldbuilding] = useState(false)
  const [isGeneratingOutline, setIsGeneratingOutline] = useState(false)
  const [activeTab, setActiveTab] = useState<'info' | 'worldbuilding' | 'outline'>('info')
  const [streamingText, setStreamingText] = useState<string>('')
  const [streamError, setStreamError] = useState<string | null>(null)
  // 追加新卷
  const [isAppendingVolume, setIsAppendingVolume] = useState(false)
  const [showAppendModal, setShowAppendModal] = useState(false)
  const [appendIntent, setAppendIntent] = useState('')
  const [appendTargetChapters, setAppendTargetChapters] = useState<number | ''>('')
  const [isPlanningChapters, setIsPlanningChapters] = useState(false)
  const [outlineTaskMeta, setOutlineTaskMeta] = useState<TaskStatus['meta'] | null>(null)
  const closeStreamRef = useRef<(() => void) | null>(null)
  const loadedProjectIdRef = useRef<string | null>(null)
  const pollTask = usePollTask()

  const loadProject = useCallback(async (id: string) => {
    try {
      const data = await projectsApi.get(id)
      setProject(data)
      if (data.status !== 'draft') {
        try {
          const wb = await projectsApi.getWorldbuilding(id)
          setWorldbuilding(wb)
        } catch (error) {
          console.error('Failed to load worldbuilding', error)
        }
        try {
          const ol = await projectsApi.getOutline(id)
          if (ol.volumes.length > 0 || ol.chapters.length > 0) setOutline(ol)
        } catch (error) {
          console.error('Failed to load outline', error)
        }
      }
    } catch (error) {
      console.error('Failed to load project:', error)
      navigate('/')
    } finally { setIsLoading(false) }
  }, [navigate])

  useEffect(() => {
    if (projectId && loadedProjectIdRef.current !== projectId) {
      loadedProjectIdRef.current = projectId
      void loadProject(projectId)
    }
    return () => { closeStreamRef.current?.() }
  }, [loadProject, projectId])

  const handleGenerateWorldbuilding = async () => {
    if (!projectId) return
    setIsGeneratingWorldbuilding(true)
    setStreamingText('')
    setStreamError(null)
    try {
      const result = await projectsApi.triggerWorldbuilding(projectId)
      const close = openWorldbuildingStream(result.task_id, {
        onToken: (chunk) => setStreamingText((prev) => prev + chunk),
        onDone: (wb) => {
          setWorldbuilding(wb)
          setIsGeneratingWorldbuilding(false)
          setStreamingText('')
          closeStreamRef.current = null
          toast.success('世界观已生成')
        },
        onError: (err) => {
          setStreamError(err)
          setIsGeneratingWorldbuilding(false)
          setStreamingText('')
          closeStreamRef.current = null
        },
      })
      closeStreamRef.current = close
    } catch (error) {
      console.error('Failed to trigger worldbuilding:', error)
      setIsGeneratingWorldbuilding(false)
    }
  }

  const handleGenerateOutline = async () => {
    if (!projectId || !worldbuilding) return
    const regenerate = Boolean(outline)
    if (regenerate && !window.confirm('重新生成卷契约会替换尚未写作的现有大纲，确定继续吗？')) return
    setIsGeneratingOutline(true)
    setStreamError(null)
    setOutlineTaskMeta(null)
    try {
      const result = await projectsApi.triggerOutline(projectId, regenerate)
      pollTask(result.task_id, {
        onUpdate: (status) => setOutlineTaskMeta(status.meta || null),
        onComplete: async () => {
          setOutline(await projectsApi.getOutline(projectId))
          setIsGeneratingOutline(false)
          toast.success('大纲已生成')
        },
        onFailed: (status) => {
          setStreamError(status.error || '大纲生成失败')
          setIsGeneratingOutline(false)
        },
        onNotFoundRetry: async () => (await projectsApi.triggerOutline(projectId, regenerate)).task_id,
      })
    } catch (error: any) {
      console.error('Failed to trigger outline:', error)
      const detail = error?.response?.data?.detail
      setStreamError(typeof detail === 'string' ? detail : detail?.message || '无法启动大纲生成')
      setIsGeneratingOutline(false)
    }
  }

  const handleAppendVolume = async () => {
    if (!projectId || !outline) return
    setIsAppendingVolume(true)
    setShowAppendModal(false)
    try {
      const payload: { intent?: string; target_chapters?: number } = {}
      if (appendIntent.trim()) payload.intent = appendIntent.trim()
      if (typeof appendTargetChapters === 'number' && appendTargetChapters > 0) {
        payload.target_chapters = appendTargetChapters
      }
      const result = await projectsApi.appendVolume(projectId, payload)
      pollTask(result.task_id, {
        onUpdate: (status) => setOutlineTaskMeta(status.meta || null),
        onComplete: async () => {
          setOutline(await projectsApi.getOutline(projectId))
          setIsAppendingVolume(false)
          toast.success('新卷已追加')
        },
        onFailed: (status) => {
          setStreamError(status.error || '追加卷任务失败')
          setIsAppendingVolume(false)
        },
      })
      setAppendIntent('')
      setAppendTargetChapters('')
    } catch (error) {
      console.error('Failed to append volume:', error)
      setIsAppendingVolume(false)
    }
  }

  const handlePlanNextChapters = async () => {
    if (!projectId) return
    setIsPlanningChapters(true)
    setStreamError(null)
    try {
      const result = await projectsApi.expandNextChapters(projectId)
      setOutlineTaskMeta({
        phase: 'queued',
        message: `等待规划第 ${result.chapter_start}-${result.chapter_end} 章`,
        active_volume: result.volume_number,
        batch_start: result.chapter_start,
        batch_end: result.chapter_end,
      })
      pollTask(result.task_id, {
        onUpdate: (status) => setOutlineTaskMeta(status.meta || null),
        onComplete: async () => {
          setOutline(await projectsApi.getOutline(projectId))
          setIsPlanningChapters(false)
          toast.success('章节规划完成')
        },
        onFailed: (status) => {
          setStreamError(status.error || '章节规划任务失败')
          setIsPlanningChapters(false)
        },
      })
    } catch (error) {
      console.error('Failed to plan next chapters:', error)
      setStreamError('无法启动下一批章节规划')
      setIsPlanningChapters(false)
    }
  }

  if (isLoading) {
    return (
      <AppShell active="project">
        <div className="flex items-center justify-center py-24 text-sm text-paper-300/40">
          <span className="mr-3 h-4 w-4 animate-spin rounded-full border-2 border-cinnabar-500 border-t-transparent" />
          加载中…
        </div>
      </AppShell>
    )
  }

  if (!project) {
    return (
      <AppShell active="project">
        <div className="empty-state">项目不存在</div>
      </AppShell>
    )
  }

  const tabs: Array<{ id: typeof activeTab; label: string }> = [
    { id: 'info', label: '项目设定' },
    { id: 'worldbuilding', label: '世界观' },
    { id: 'outline', label: '大纲' },
  ]

  return (
    <AppShell
      active="project"
      projectId={projectId}
      projectTitle={project.title}
      headerRight={
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate(`/project/${projectId}/workbench`)}
            className="secondary-button"
          >
            生产控制台
          </button>
          <span className={`status-chip status-${project.status}`}>{project.status}</span>
        </div>
      }
    >
      <div className="mx-auto max-w-5xl">
        <h1 className="font-display text-3xl font-semibold text-paper-50">{project.title}</h1>

        <div className="mt-6 flex gap-1 border-b border-ink-700/60">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`relative px-4 py-2.5 text-sm font-medium transition ${
                activeTab === tab.id
                  ? 'text-cinnabar-300'
                  : 'text-paper-300/45 hover:text-paper-100'
              }`}
            >
              {tab.label}
              {activeTab === tab.id && (
                <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-cinnabar-500" />
              )}
            </button>
          ))}
        </div>

        <div className="mt-6">
          {activeTab === 'info' && (
            <div className="ink-card p-6 animate-fade-up">
              <div className="space-y-5">
                <div>
                  <label className="section-label">核心创意</label>
                  <p className="font-serif text-[1.0625rem] leading-relaxed text-paper-100">{project.core_idea}</p>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="field-label">类型</label>
                    <p className="mt-1 text-paper-100">{project.genre || '未设定'}</p>
                  </div>
                  <div>
                    <label className="field-label">风格</label>
                    <p className="mt-1 text-paper-100">{project.tone_style || '未设定'}</p>
                  </div>
                  <div>
                    <label className="field-label">目标字数</label>
                    <p className="mt-1 text-paper-100">{project.target_word_count.toLocaleString()} 字</p>
                  </div>
                  <div>
                    <label className="field-label">目标章节数</label>
                    <p className="mt-1 text-paper-100">{project.target_chapter_count} 章</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'worldbuilding' && (
            <div className="animate-fade-up">
              <WorldbuildingTab
                value={worldbuilding}
                generating={isGeneratingWorldbuilding}
                streamingText={streamingText}
                error={streamError}
                onGenerate={() => void handleGenerateWorldbuilding()}
                onDismissError={() => setStreamError(null)}
              />
            </div>
          )}

          {activeTab === 'outline' && (
            <div className="animate-fade-up space-y-6">
              <div className="ink-card p-6">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <h2 className="font-display text-lg font-semibold text-paper-50">小说大纲</h2>
                  <div className="flex gap-2">
                    {outline && (
                      <button
                        type="button"
                        onClick={handlePlanNextChapters}
                        disabled={isPlanningChapters || outline.volumes.every(vol => vol.is_complete)}
                        className="primary-button"
                      >
                        {isPlanningChapters ? '规划中…' : outline.volumes.every(vol => vol.is_complete) ? '全部章节已规划' : '规划接下来 5 章'}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={handleGenerateOutline}
                      disabled={isGeneratingOutline || !worldbuilding}
                      className="secondary-button"
                      title={!worldbuilding ? '请先生成世界观' : ''}
                    >
                      {isGeneratingOutline ? '生成中…' : (outline ? '重新生成卷契约' : '生成大纲')}
                    </button>
                  </div>
                </div>

                {streamError && (
                  <div className="alert-error mb-4">
                    <span className="flex-1">生成失败：{streamError}</span>
                    <button type="button" onClick={() => setStreamError(null)} className="text-xs underline">关闭</button>
                  </div>
                )}

                {(isGeneratingOutline || isPlanningChapters || isAppendingVolume) && (
                  <div className="mb-4 space-y-2 text-paper-200/60">
                    <div className="flex items-center gap-3">
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-cinnabar-500 border-t-transparent" />
                      <span>{outlineTaskMeta?.message || 'AI 正在构建大纲，请稍候…'}</span>
                    </div>
                    {outlineTaskMeta?.completed_chapter_count !== undefined && outlineTaskMeta?.target_chapter_count && (
                      <div className="text-xs text-paper-300/45">
                        已规划 {outlineTaskMeta.completed_chapter_count} / {outlineTaskMeta.target_chapter_count} 章
                      </div>
                    )}
                  </div>
                )}

                {outline && !isGeneratingOutline && (
                  <div className="space-y-6">
                    {/* ── 卷结构区（滚动规划核心 UI）── */}
                    <div>
                      <div className="mb-3 flex items-center justify-between">
                        <h3 className="section-label mb-0">卷结构</h3>
                        <button
                          type="button"
                          onClick={() => setShowAppendModal(true)}
                          disabled={isAppendingVolume || !outline.volumes.every(vol => vol.is_complete)}
                          className="action-button !min-h-8 !py-1 text-xs"
                          title={!outline.volumes.every(vol => vol.is_complete) ? '请先完成当前所有卷的章节规划' : ''}
                        >
                          <Plus size={13} /> {isAppendingVolume ? '追加中…' : '追加新卷'}
                        </button>
                      </div>
                      <div className="grid gap-3">
                        {outline.volumes.map((vol) => {
                          const isExpanded = vol.has_detail
                          const volChapters = outline.chapters.filter(ch => ch.volume === vol.number)
                          const chapterCount = `${vol.planned_chapter_count} / ${vol.target_chapter_count} 章`
                          const badge = VOL_STATUS[vol.status] || { label: vol.status, cls: 'border-ink-600 bg-ink-800 text-paper-300/50' }

                          return (
                            <div key={vol.number} className="ink-panel p-4">
                              <div className="flex items-start justify-between">
                                <div className="flex-1">
                                  <div className="mb-1 flex items-center gap-2">
                                    <span className="font-serif text-base font-semibold text-paper-50">
                                      第{vol.number}卷 · {vol.title}
                                    </span>
                                    <span className={`status-chip ${badge.cls}`}>{badge.label}</span>
                                  </div>
                                  <div className="text-sm text-paper-200/60">
                                    核心冲突：{vol.core_conflict}
                                  </div>
                                  <div className="mt-1 text-xs text-cinnabar-300/80">
                                    角色弧线：{vol.character_arc_stage}
                                  </div>
                                  {vol.summary && (
                                    <div className="mt-1 text-xs italic text-paper-300/40">
                                      概要：{vol.summary}
                                    </div>
                                  )}
                                  <div className="mt-1 text-xs text-paper-300/40">
                                    章号范围 {vol.chapter_start}-{vol.chapter_end}，已规划 {chapterCount}
                                  </div>
                                  {vol.contract.ending_state && (
                                    <div className="mt-1 text-xs text-paper-300/40">
                                      卷末锚点：{vol.contract.ending_state}
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* 已规划章节列表（缩进展示） */}
                              {isExpanded && volChapters.length > 0 && (
                                <div className="mt-3 space-y-2 border-l-2 border-ink-600 pl-3">
                                  {volChapters.map((ch) => (
                                    <div key={ch.number} className="rounded-md bg-ink-800/70 p-2.5 text-sm">
                                      <div className="flex items-center justify-between gap-3">
                                        <div className="flex min-w-0 items-center gap-2">
                                          <span className="shrink-0 text-xs text-paper-300/40">第{ch.number}章</span>
                                          <span className="truncate text-paper-100">{ch.title}</span>
                                        </div>
                                        <button
                                          type="button"
                                          onClick={() => navigate(`/project/${projectId}/write/${ch.number}`)}
                                          className="action-button !min-h-7 shrink-0 !py-1 text-xs"
                                        >
                                          <PenLine size={12} /> 写作
                                        </button>
                                      </div>
                                      <div className="mt-1 text-xs text-paper-300/45">目标：{ch.goal}</div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>

                    {/* ── 伏笔登记 ── */}
                    <div>
                      <h3 className="section-label">伏笔登记（共 {outline.foreshadowing_registry.length} 个）</h3>
                      <div className="space-y-2">
                        {outline.foreshadowing_registry.map((fs, i) => (
                          <div key={i} className="ink-panel flex flex-wrap items-center gap-x-4 gap-y-1 p-3 text-sm">
                            <span className="font-medium text-gold-300">{fs.name}</span>
                            <span className="text-paper-300/50">第{fs.sow_chapter}章埋下</span>
                            {fs.reap_chapter && <span className="text-jade-400">→ 第{fs.reap_chapter}章回收</span>}
                            <span className="text-xs text-paper-300/40">{fs.description}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {!outline && !isGeneratingOutline && (
                  <div className="flex flex-col items-center gap-3 py-10 text-center">
                    <Sparkles size={22} className="text-gold-400" />
                    <p className="text-sm text-paper-300/45">
                      {worldbuilding ? '点击上方按钮生成大纲' : '请先在“世界观”标签页生成世界观'}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {showAppendModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/70 px-4 backdrop-blur-sm animate-fade-in"
          onMouseDown={() => setShowAppendModal(false)}
        >
          <div
            className="ink-card w-full max-w-md p-6 shadow-lift animate-scale-in"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 className="font-display text-xl font-semibold text-paper-50">追加新卷</h3>
            <p className="mt-1 text-sm text-paper-300/45">
              AI 将基于已写大纲续接一个新卷（不重生成旧章节、不动旧伏笔）。
            </p>
            <div className="mt-5 space-y-4">
              <div>
                <label className="field-label" htmlFor="av-intent">创作意图（可选）</label>
                <textarea
                  id="av-intent"
                  value={appendIntent}
                  onChange={(e) => setAppendIntent(e.target.value)}
                  placeholder="例如：加点感情戏 / 主角去秘境探索 / 揭示身世真相"
                  className="field-textarea h-20"
                  maxLength={500}
                />
              </div>
              <div>
                <label className="field-label" htmlFor="av-chapters">新卷章数（可选）</label>
                <input
                  id="av-chapters"
                  type="number"
                  min={3}
                  max={50}
                  value={appendTargetChapters}
                  onChange={(e) => {
                    const v = e.target.value
                    if (v === '') setAppendTargetChapters('')
                    else {
                      const n = parseInt(v, 10)
                      if (!isNaN(n)) setAppendTargetChapters(Math.max(3, Math.min(50, n)))
                    }
                  }}
                  placeholder="留空则自动估算"
                  className="field-input"
                />
              </div>
            </div>
            <div className="mt-6 flex gap-3">
              <button type="button" onClick={() => setShowAppendModal(false)} className="secondary-button flex-1">
                取消
              </button>
              <button type="button" onClick={handleAppendVolume} className="primary-button flex-1">
                确认追加
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  )
}
