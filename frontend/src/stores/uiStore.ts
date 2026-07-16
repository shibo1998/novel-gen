import { create } from 'zustand'

export type ToastKind = 'success' | 'error' | 'info'

export interface Toast {
  id: string
  kind: ToastKind
  message: string
  /** optional secondary line */
  detail?: string
}

interface UIState {
  toasts: Toast[]
  paletteOpen: boolean
  pushToast: (kind: ToastKind, message: string, detail?: string) => void
  dismissToast: (id: string) => void
  openPalette: () => void
  closePalette: () => void
  togglePalette: () => void
  setPaletteOpen: (open: boolean) => void
}

let seq = 0

export const useUIStore = create<UIState>((set) => ({
  toasts: [],
  paletteOpen: false,

  pushToast: (kind, message, detail) => {
    const id = `t${Date.now()}-${seq++}`
    set((state) => ({ toasts: [...state.toasts, { id, kind, message, detail }] }))
    // auto-dismiss: errors linger a touch longer
    const ttl = kind === 'error' ? 6000 : 3600
    window.setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }))
    }, ttl)
  },

  dismissToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  openPalette: () => set({ paletteOpen: true }),
  closePalette: () => set({ paletteOpen: false }),
  togglePalette: () => set((state) => ({ paletteOpen: !state.paletteOpen })),
  setPaletteOpen: (open) => set({ paletteOpen: open }),
}))

/** Convenience helper usable outside React (api layers, stores). */
export const toast = {
  success: (message: string, detail?: string) => useUIStore.getState().pushToast('success', message, detail),
  error: (message: string, detail?: string) => useUIStore.getState().pushToast('error', message, detail),
  info: (message: string, detail?: string) => useUIStore.getState().pushToast('info', message, detail),
}
