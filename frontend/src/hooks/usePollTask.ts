import { useCallback, useEffect, useRef } from 'react'
import { projectsApi } from '@/api/projects'
import type { TaskStatus } from '@/types/api'

interface PollOptions {
  onUpdate?: (status: TaskStatus) => void
  onComplete: (status: TaskStatus) => void | Promise<void>
  onFailed: (status: TaskStatus) => void
  onNotFoundRetry?: () => Promise<string | null>
  intervalMs?: number
}

export function usePollTask() {
  const timers = useRef<Set<number>>(new Set())
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    const activeTimers = timers.current
    return () => {
      mounted.current = false
      activeTimers.forEach(window.clearTimeout)
      activeTimers.clear()
    }
  }, [])

  return useCallback((initialTaskId: string, options: PollOptions) => {
    let taskId = initialTaskId
    let retriedNotFound = false

    const schedule = (delay: number) => {
      const timer = window.setTimeout(() => {
        timers.current.delete(timer)
        void poll()
      }, delay)
      timers.current.add(timer)
    }

    const poll = async () => {
      if (!mounted.current) return
      try {
        const status = await projectsApi.getTaskStatus(taskId)
        if (!mounted.current) return
        options.onUpdate?.(status)
        if (status.status === 'completed') await options.onComplete(status)
        else if (['failed', 'orphaned', 'interrupted'].includes(status.status)) options.onFailed(status)
        else schedule(options.intervalMs ?? 2000)
      } catch (error: any) {
        if (error?.response?.status === 404 && !retriedNotFound && options.onNotFoundRetry) {
          retriedNotFound = true
          const replacement = await options.onNotFoundRetry()
          if (replacement) {
            taskId = replacement
            schedule(500)
            return
          }
        }
        console.error('Task polling failed', error)
        options.onFailed({ task_id: taskId, status: 'failed', error: '任务状态查询失败' })
      }
    }

    void poll()
  }, [])
}
