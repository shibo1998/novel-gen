import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, RotateCcw } from 'lucide-react'
import { workbenchApi } from '@/api/workbench'
import { projectsApi } from '@/api/projects'
import { useGenerationStore } from '@/stores/generationStore'
import type { ProjectTask } from '@/types/workbench'

export function TasksPanel({ projectId }: { projectId: string }) {
  const [tasks, setTasks] = useState<ProjectTask[]>([])
  const [loading, setLoading] = useState(true)
  const [recoveringId, setRecoveringId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const beginRecovery = useGenerationStore((state) => state.beginRecovery)
  const complete = useGenerationStore((state) => state.complete)
  const fail = useGenerationStore((state) => state.fail)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setTasks(await workbenchApi.listTasks(projectId))
    } catch {
      setError('无法读取持久任务')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { void load() }, [load])

  const recover = async (task: ProjectTask) => {
    if (!task.scene_id) return
    setRecoveringId(task.task_id)
    setError(null)
    try {
      const recovery = await workbenchApi.recoverTask(task.task_id)
      beginRecovery(task.scene_id, recovery.task_id)
      for (let attempt = 0; attempt < 120; attempt += 1) {
        const status = await projectsApi.getTaskStatus(recovery.task_id)
        if (status.status === 'completed') {
          complete()
          break
        }
        if (status.status === 'failed' || status.status === 'orphaned') {
          const message = status.error || '场景重新生成失败'
          fail(message)
          throw new Error(message)
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000))
      }
      await load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '恢复任务失败')
    } finally {
      setRecoveringId(null)
    }
  }

  return (
    <section aria-labelledby="tasks-heading" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 id="tasks-heading" className="text-base font-semibold text-white">持久任务</h2>
          <p className="mt-1 text-sm text-paper-300/45">中断任务按冻结快照重新生成整个场景。</p>
        </div>
        <button type="button" onClick={() => void load()} className="icon-button" title="刷新任务">
          <RefreshCw size={16} aria-hidden="true" />
          <span className="sr-only">刷新任务</span>
        </button>
      </div>
      {error && <p role="alert" className="alert-error">{error}</p>}
      {loading ? <p className="empty-state">正在读取任务...</p> : tasks.length === 0 ? (
        <p className="empty-state">暂无持久写作任务</p>
      ) : (
        <div className="table-shell">
          <table className="data-table">
            <thead><tr><th>类型</th><th>状态</th><th>恢复</th><th>成本</th><th><span className="sr-only">操作</span></th></tr></thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.task_id}>
                  <td><div className="font-medium text-paper-100">{task.task_type}</div><div className="mono-id">{task.task_id.slice(0, 12)}</div></td>
                  <td><span className={`status-chip status-${task.status}`}>{task.status}</span>{task.error && <div className="mt-1 max-w-xs text-xs text-cinnabar-300">{task.error}</div>}</td>
                  <td className="text-paper-200/70">{task.recovery_attempt_count}/{task.max_recovery_attempts}</td>
                  <td className="text-paper-200/70">${task.spent_cost.toFixed(4)}</td>
                  <td className="text-right">
                    <button
                      type="button"
                      disabled={!task.can_recover || recoveringId !== null}
                      onClick={() => void recover(task)}
                      className="action-button"
                    >
                      <RotateCcw size={15} aria-hidden="true" />
                      {recoveringId === task.task_id ? '重新生成中' : '重新生成'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
