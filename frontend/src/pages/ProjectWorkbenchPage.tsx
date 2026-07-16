import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Activity, BookCopy, GitCompare, Palette, SearchCheck, Users } from 'lucide-react'
import { projectsApi, type Project } from '@/api/projects'
import { AppShell } from '@/components/AppShell'
import { CharactersPanel } from '@/components/workbench/CharactersPanel'
import { DhoPanel } from '@/components/workbench/DhoPanel'
import { ReviewsPanel } from '@/components/workbench/ReviewsPanel'
import { StylePanel } from '@/components/workbench/StylePanel'
import { TasksPanel } from '@/components/workbench/TasksPanel'
import { VersionsPanel } from '@/components/workbench/VersionsPanel'

type WorkbenchTab = 'tasks' | 'reviews' | 'characters' | 'versions' | 'dho' | 'style'

const tabs = [
  { id: 'tasks' as const, label: '任务', icon: Activity },
  { id: 'reviews' as const, label: '审核', icon: SearchCheck },
  { id: 'characters' as const, label: '角色', icon: Users },
  { id: 'versions' as const, label: '正文版本', icon: BookCopy },
  { id: 'dho' as const, label: '大纲变更', icon: GitCompare },
  { id: 'style' as const, label: '风格', icon: Palette },
]

export default function ProjectWorkbenchPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [project, setProject] = useState<Project | null>(null)
  const [activeTab, setActiveTab] = useState<WorkbenchTab>('tasks')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) return
    void projectsApi.get(projectId).then(setProject).catch(() => setError('项目不存在或无访问权限'))
  }, [projectId])

  if (!projectId) return null

  return (
    <AppShell
      active="workbench"
      projectId={projectId}
      projectTitle={project?.title}
      headerRight={project && <span className={`status-chip status-${project.status}`}>{project.status}</span>}
    >
      <div className="mx-auto max-w-6xl">
        <div className="mb-6">
          <h1 className="font-display text-2xl font-semibold text-paper-50">生产控制台</h1>
          <p className="mt-1 text-sm text-paper-300/45">任务 · 审校 · 角色 · 版本 · 大纲变更 · 风格</p>
        </div>

        <div className="grid gap-0 lg:grid-cols-[13rem_minmax(0,1fr)]">
          <nav
            aria-label="工作台模块"
            className="flex gap-1 overflow-x-auto border-b border-ink-700 pb-3 lg:block lg:border-b-0 lg:border-r lg:border-ink-700/60 lg:pb-0 lg:pr-5"
          >
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  type="button"
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`workbench-tab ${activeTab === tab.id ? 'workbench-tab-active' : ''}`}
                >
                  <Icon size={16} aria-hidden="true" />
                  <span>{tab.label}</span>
                </button>
              )
            })}
          </nav>
          <div className="min-w-0 pt-5 lg:pl-7 lg:pt-0">
            {error ? (
              <p role="alert" className="alert-error">{error}</p>
            ) : (
              <>
                {activeTab === 'tasks' && <TasksPanel projectId={projectId} />}
                {activeTab === 'reviews' && <ReviewsPanel projectId={projectId} />}
                {activeTab === 'characters' && <CharactersPanel projectId={projectId} />}
                {activeTab === 'versions' && <VersionsPanel projectId={projectId} />}
                {activeTab === 'dho' && <DhoPanel projectId={projectId} />}
                {activeTab === 'style' && <StylePanel projectId={projectId} />}
              </>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  )
}
