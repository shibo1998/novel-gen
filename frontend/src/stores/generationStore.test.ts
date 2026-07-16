import { beforeEach, describe, expect, it } from 'vitest'
import { useGenerationStore } from './generationStore'

describe('generationStore', () => {
  beforeEach(() => useGenerationStore.getState().reset())

  it('clears the old stream buffer when full-scene recovery starts', () => {
    const store = useGenerationStore.getState()
    store.begin('scene-1', '旧的半段草稿')
    store.beginRecovery('scene-1', 'recovery-task')
    useGenerationStore.getState().appendToken('新的完整场景')

    expect(useGenerationStore.getState()).toMatchObject({
      streamStatus: 'recovering',
      streamBuffer: '新的完整场景',
      taskId: 'recovery-task',
    })
  })
})
