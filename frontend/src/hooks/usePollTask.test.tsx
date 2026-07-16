import { StrictMode } from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { projectsApi } from '@/api/projects'
import { usePollTask } from './usePollTask'

vi.mock('@/api/projects', () => ({
  projectsApi: { getTaskStatus: vi.fn() },
}))

describe('usePollTask', () => {
  beforeEach(() => vi.clearAllMocks())

  it('continues polling after the StrictMode effect cleanup/setup cycle', async () => {
    vi.mocked(projectsApi.getTaskStatus).mockResolvedValue({
      task_id: 'task-1',
      status: 'completed',
      result: {},
      meta: {},
    })
    const onComplete = vi.fn()
    const { result } = renderHook(() => usePollTask(), {
      wrapper: ({ children }) => <StrictMode>{children}</StrictMode>,
    })

    result.current('task-1', { onComplete, onFailed: vi.fn() })

    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce())
  })
})
