import { create } from 'zustand'

export type GenerationStreamStatus = 'idle' | 'streaming' | 'recovering' | 'completed' | 'error'

interface GenerationState {
  sceneId: string | null
  taskId: string | null
  streamStatus: GenerationStreamStatus
  streamBuffer: string
  error: string | null
  begin: (sceneId: string, initialContent?: string) => void
  beginRecovery: (sceneId: string, taskId?: string) => void
  appendToken: (token: string) => void
  complete: () => void
  fail: (message: string) => void
  stop: () => void
  reset: () => void
}

const initialState = {
  sceneId: null,
  taskId: null,
  streamStatus: 'idle' as GenerationStreamStatus,
  streamBuffer: '',
  error: null,
}

export const useGenerationStore = create<GenerationState>((set) => ({
  ...initialState,
  begin: (sceneId, initialContent = '') => set({
    sceneId,
    taskId: null,
    streamStatus: 'streaming',
    streamBuffer: initialContent,
    error: null,
  }),
  beginRecovery: (sceneId, taskId = '') => set({
    sceneId,
    taskId,
    streamStatus: 'recovering',
    streamBuffer: '',
    error: null,
  }),
  appendToken: (token) => set((state) => ({ streamBuffer: state.streamBuffer + token })),
  complete: () => set({ streamStatus: 'completed', error: null }),
  fail: (message) => set({ streamStatus: 'error', error: message }),
  stop: () => set((state) => ({
    streamStatus: state.streamBuffer ? 'completed' : 'idle',
  })),
  reset: () => set(initialState),
}))
