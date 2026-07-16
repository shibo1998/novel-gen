import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Plus, Sparkles } from 'lucide-react'
import { projectsApi, Project, CreateProjectRequest } from '@/api/projects'
import { toast } from '@/stores/uiStore'
import { AppShell } from '@/components/AppShell'

type ComplianceIssue = { term: string; category: string; count: number }

export default function DashboardPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [projects, setProjects] = useState<Project[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newProject, setNewProject] = useState<CreateProjectRequest>({
    title: '',
    core_idea: '',
    genre: '',
    tone_style: '',
    target_chapter_count: 90,
  })
  // 合规检测相关
  const [complianceIssues, setComplianceIssues] = useState<ComplianceIssue[]>([])
  const [isChecking, setIsChecking] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  useEffect(() => {
    loadProjects()
  }, [])

  // 命令面板通过 /?new=1 唤起新建弹窗
  useEffect(() => {
    if (searchParams.get('new') === '1') {
      setShowCreateModal(true)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

  // debounced compliance check: 800ms 内不再触发
  useEffect(() => {
    const text = newProject.core_idea
    if (!text.trim()) {
      setComplianceIssues([])
      return
    }
    setIsChecking(true)
    const timer = setTimeout(async () => {
      try {
        const result = await projectsApi.checkCompliance(text)
        setComplianceIssues(result.issues)
      } catch (e) {
        // 检测失败不阻塞用户，宁放过
        console.warn('compliance check failed', e)
      } finally {
        setIsChecking(false)
      }
    }, 800)
    return () => clearTimeout(timer)
  }, [newProject.core_idea])

  const loadProjects = async () => {
    try {
      const data = await projectsApi.list()
      setProjects(data)
    } catch (error) {
      console.error('Failed to load projects:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError(null)
    // 前端卡一道：有不合规词直接挡
    if (complianceIssues.length > 0) {
      setCreateError('请先移除核心创意中的真实地名/品牌后创建')
      return
    }
    try {
      const project = await projectsApi.create(newProject)
      setProjects([project, ...projects])
      setShowCreateModal(false)
      setNewProject({ title: '', core_idea: '', genre: '', tone_style: '', target_chapter_count: 90 })
      setComplianceIssues([])
      setCreateError(null)
      toast.success('项目已创建', project.title)
      navigate(`/project/${project.id}`)
    } catch (error: any) {
      console.error('Failed to create project:', error)
      const detail = error?.response?.data?.detail
      const message = typeof detail === 'string' ? detail : '创建失败，请稍后重试'
      setCreateError(message)
      toast.error(message)
    }
  }

  return (
    <AppShell active="dashboard">
      <div className="mx-auto max-w-6xl">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-semibold text-paper-50">我的项目</h1>
            <p className="mt-1 text-sm text-paper-300/45">
              {projects.length > 0 ? `共 ${projects.length} 部作品` : '从一个念头开始，写成一部长篇'}
            </p>
          </div>
          <button type="button" onClick={() => setShowCreateModal(true)} className="primary-button">
            <Plus size={16} /> 新建项目
          </button>
        </div>

        <div className="mt-8">
          {isLoading ? (
            <div className="flex items-center justify-center py-24 text-sm text-paper-300/40">
              <span className="mr-3 h-4 w-4 animate-spin rounded-full border-2 border-cinnabar-500 border-t-transparent" />
              加载中…
            </div>
          ) : projects.length === 0 ? (
            <div className="empty-state">
              <Sparkles size={22} className="mx-auto mb-3 text-gold-400" />
              <p className="mb-4 text-paper-300/50">还没有项目</p>
              <button type="button" onClick={() => setShowCreateModal(true)} className="action-button mx-auto">
                <Plus size={15} /> 创建第一个项目
              </button>
            </div>
          ) : (
            <div className="stagger grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {projects.map((project) => (
                <Link
                  key={project.id}
                  to={`/project/${project.id}`}
                  className="ink-card group flex flex-col p-5 transition hover:-translate-y-0.5 hover:border-cinnabar-500/50 hover:shadow-lift"
                >
                  <h3 className="font-serif text-lg font-semibold text-paper-50 transition group-hover:text-cinnabar-200">
                    {project.title}
                  </h3>
                  <p className="mt-2 line-clamp-2 flex-1 text-sm leading-relaxed text-paper-300/50">
                    {project.core_idea}
                  </p>
                  <div className="mt-4 flex items-center justify-between">
                    <span className="text-xs text-paper-300/40">{project.genre || '未分类'}</span>
                    <span className={`status-chip status-${project.status}`}>{project.status}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {showCreateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/70 px-4 backdrop-blur-sm animate-fade-in"
          onMouseDown={() => setShowCreateModal(false)}
        >
          <div
            className="ink-card w-full max-w-md p-6 shadow-lift animate-scale-in"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 className="font-display text-xl font-semibold text-paper-50">新建项目</h3>
            <p className="mt-1 text-sm text-paper-300/45">先给作品定个方向，其余交给智能体。</p>
            <form onSubmit={handleCreateProject} className="mt-5 space-y-4">
              <div>
                <label className="field-label" htmlFor="np-title">标题</label>
                <input
                  id="np-title"
                  type="text"
                  value={newProject.title}
                  onChange={(e) => setNewProject({ ...newProject, title: e.target.value })}
                  className="field-input"
                  required
                />
              </div>

              <div>
                <label className="field-label" htmlFor="np-idea">核心创意</label>
                <textarea
                  id="np-idea"
                  value={newProject.core_idea}
                  onChange={(e) => setNewProject({ ...newProject, core_idea: e.target.value })}
                  className="field-textarea h-32"
                  required
                />
                {isChecking && <div className="mt-1 text-xs text-paper-300/40">合规检测中…</div>}
                {!isChecking && complianceIssues.length > 0 && (
                  <div className="mt-2 rounded-md border border-gold-500/40 bg-gold-500/10 p-3">
                    <div className="mb-1 text-sm font-medium text-gold-300">
                      ⚠️ 检测到 {complianceIssues.length} 处不合规内容
                    </div>
                    <div className="space-y-1 text-xs text-gold-300/80">
                      {complianceIssues.map((i, k) => {
                        const sensitiveCats = ['real_sensitive', 'real_sensitive_event', 'real_person', 'real_political', 'real_sensitive_org']
                        const isSensitive = sensitiveCats.includes(i.category)
                        return (
                          <div key={k}>
                            「{i.term}」
                            {isSensitive ? '（敏感）' : `（${i.category}）`}
                            — 请改写为虚构名称
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="field-label" htmlFor="np-genre">类型</label>
                  <input
                    id="np-genre"
                    type="text"
                    value={newProject.genre || ''}
                    onChange={(e) => setNewProject({ ...newProject, genre: e.target.value })}
                    className="field-input"
                    placeholder="奇幻/科幻/都市..."
                  />
                </div>

                <div className="flex-1">
                  <label className="field-label" htmlFor="np-tone">风格</label>
                  <input
                    id="np-tone"
                    type="text"
                    value={newProject.tone_style || ''}
                    onChange={(e) => setNewProject({ ...newProject, tone_style: e.target.value })}
                    className="field-input"
                    placeholder="轻松/严肃/黑暗..."
                  />
                </div>
              </div>

              <div>
                <label className="field-label" htmlFor="np-chapters">目标章节数</label>
                <input
                  id="np-chapters"
                  type="number"
                  min={10}
                  max={2000}
                  step={1}
                  value={newProject.target_chapter_count ?? 90}
                  onChange={(e) => setNewProject({ ...newProject, target_chapter_count: Math.max(10, Math.min(2000, parseInt(e.target.value, 10) || 90)) })}
                  className="field-input"
                  placeholder="默认 90，例：100~500"
                />
                <p className="mt-1 text-xs text-paper-300/40">
                  全书预期章节规模，骨架与每卷细纲都会按此切分。写作过程中可随时"追加新卷"扩容。
                </p>
              </div>

              {createError && <p className="alert-error">{createError}</p>}

              <div className="mt-6 flex gap-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="secondary-button flex-1"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={complianceIssues.length > 0 || isChecking}
                  className="primary-button flex-1"
                >
                  {complianceIssues.length > 0 ? '请先修改核心创意' : '创建'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  )
}
