import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useGenerationStore } from '@/stores/generationStore'
import { useStreamingWrite } from './useStreamingWrite'

describe('useStreamingWrite', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token')
    useGenerationStore.getState().reset()
  })

  it('parses split SSE frames and replaces interrupted content on recovery', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"type":"recover'))
        controller.enqueue(encoder.encode('ing","offset":0}\n\ndata: {"type":"token","content":"新文本"}\n\n'))
        controller.enqueue(encoder.encode('data: {"type":"done","total_tokens":3,"word_count":3}\n\n'))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { status: 200 })))
    useGenerationStore.getState().begin('scene-1', '旧文本')
    const { result } = renderHook(() => useStreamingWrite({ sceneId: 'scene-1' }))

    await act(async () => { await result.current.startWriting(2) })

    expect(result.current.content).toBe('新文本')
    expect(useGenerationStore.getState().streamStatus).toBe('completed')
  })
})
