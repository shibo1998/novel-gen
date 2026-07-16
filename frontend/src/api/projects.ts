import { apiClient } from './client'
import type { TaskStatus, WorldbuildingResult, OutlineResult, VolumeStatus } from '@/types/api'
import type { Project } from '@/types/domain'

export type { Project } from '@/types/domain'

export interface CreateProjectRequest {
  title: string
  core_idea: string
  genre?: string
  tone_style?: string
  target_word_count?: number
  target_chapter_count?: number
}

export const projectsApi = {
  list: async (params?: { skip?: number; limit?: number; status?: string }): Promise<Project[]> => {
    const response = await apiClient.get<Project[]>('/api/projects', { params })
    return response.data
  },

  get: async (projectId: string): Promise<Project> => {
    const response = await apiClient.get<Project>(`/api/projects/${projectId}`)
    return response.data
  },

  create: async (data: CreateProjectRequest): Promise<Project> => {
    const response = await apiClient.post<Project>('/api/projects', data)
    return response.data
  },

  update: async (projectId: string, data: Partial<CreateProjectRequest>): Promise<Project> => {
    const response = await apiClient.put<Project>(`/api/projects/${projectId}`, data)
    return response.data
  },

  delete: async (projectId: string): Promise<void> => {
    await apiClient.delete(`/api/projects/${projectId}`)
  },

  // 世界观
  triggerWorldbuilding: async (projectId: string, regenerate = false) => {
    const response = await apiClient.post<{ task_id: string; status: string }>(
      `/api/projects/${projectId}/worldbuilding`,
      { regenerate }
    )
    return response.data
  },

  getWorldbuilding: async (projectId: string): Promise<WorldbuildingResult> => {
    const response = await apiClient.get<WorldbuildingResult>(`/api/projects/${projectId}/worldbuilding`)
    return response.data
  },

  // 大纲
  triggerOutline: async (projectId: string, regenerate = false) => {
    const response = await apiClient.post<{ task_id: string; status: string }>(
      `/api/projects/${projectId}/outline`,
      { regenerate }
    )
    return response.data
  },

  getOutline: async (projectId: string): Promise<OutlineResult> => {
    const response = await apiClient.get<OutlineResult>(`/api/projects/${projectId}/outline`)
    return response.data
  },

  // 追加新卷（Phase 8 滚动规划）
  appendVolume: async (projectId: string, payload: { intent?: string; target_chapters?: number } = {}) => {
    const response = await apiClient.post<{ task_id: string; status: string }>(
      `/api/projects/${projectId}/volumes/append`,
      payload
    )
    return response.data
  },

  // 展开指定卷细纲（滚动规划）
  expandVolume: async (projectId: string, volNum: number) => {
    const response = await apiClient.post<{ task_id: string; status: string; volume_number: number }>(
      `/api/projects/${projectId}/volumes/expand/${volNum}`,
      {}
    )
    return response.data
  },

  // 按章节滚动：规划接下来至多 5 章
  expandNextChapters: async (projectId: string) => {
    const response = await apiClient.post<{
      task_id: string
      status: string
      volume_number: number
      chapter_start: number
      chapter_end: number
    }>(`/api/projects/${projectId}/outline/expand-next`, {})
    return response.data
  },

  // 列出所有卷
  listVolumes: async (projectId: string) => {
    const response = await apiClient.get<VolumeStatus[]>(`/api/projects/${projectId}/volumes`)
    return response.data
  },

  // 任务状态
  getTaskStatus: async (taskId: string): Promise<TaskStatus> => {
    const response = await apiClient.get<TaskStatus>(`/api/tasks/${taskId}`)
    return response.data
  },

  // 合规预检
  checkCompliance: async (text: string): Promise<{ compliant: boolean; issues: { term: string; category: string; count: number }[] }> => {
    const response = await apiClient.post<{ compliant: boolean; issues: { term: string; category: string; count: number }[] }>(
      `/api/projects/compliance/check`,
      { text }
    )
    return response.data
  },
}
