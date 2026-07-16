import { apiClient } from './client'
import type {
  CharacterCard,
  CharacterMemory,
  CharacterProfile,
  ContentVersion,
  DhoCandidate,
  ProjectChapter,
  ProjectTask,
  ReviewItem,
  SceneSummary,
  StyleVersion,
} from '@/types/workbench'

export const workbenchApi = {
  listChapters: async (projectId: string) =>
    (await apiClient.get<ProjectChapter[]>(`/api/projects/${projectId}/chapters`)).data,

  listScenes: async (projectId: string, chapterId: string) =>
    (await apiClient.get<SceneSummary[]>(`/api/projects/${projectId}/chapters/${chapterId}/scenes`)).data,

  expandChapter: async (projectId: string, chapterId: string) =>
    (await apiClient.post<{ task_id: string | null; status: string }>(
      `/api/projects/${projectId}/chapters/${chapterId}/expand`,
      { regenerate: false },
    )).data,

  saveScene: async (sceneId: string, content: string) =>
    (await apiClient.post<{ message: string; word_count: number }>(
      `/api/v1/scenes/${sceneId}/save`,
      { content },
    )).data,

  listTasks: async (projectId: string) =>
    (await apiClient.get<ProjectTask[]>(`/api/projects/${projectId}/tasks`)).data,

  recoverTask: async (taskId: string) =>
    (await apiClient.post<{ task_id: string; status: string; recovery_attempt: number }>(
      `/api/tasks/${taskId}/recover`,
      {},
    )).data,

  listReviews: async (projectId: string, status = 'open') =>
    (await apiClient.get<ReviewItem[]>(`/api/projects/${projectId}/reviews`, {
      params: { review_status: status },
    })).data,

  resolveReview: async (reviewId: string, resolution: Record<string, unknown>) =>
    (await apiClient.post<{ status: string }>(`/api/reviews/${reviewId}/resolve`, { resolution })).data,

  listCharacters: async (projectId: string) =>
    (await apiClient.get<CharacterCard[]>(`/api/projects/${projectId}/characters`)).data,

  createCharacter: async (
    projectId: string,
    payload: { name: string; display_name: string; description: string; profile: CharacterProfile },
  ) => (await apiClient.post<CharacterCard>(`/api/projects/${projectId}/characters`, payload)).data,

  updateCharacter: async (
    characterId: string,
    payload: {
      description?: string
      profile: CharacterProfile
      chapter_applied: number
      change_summary: string
    },
  ) => (await apiClient.put<CharacterCard>(`/api/characters/${characterId}`, payload)).data,

  deleteCharacter: async (characterId: string) =>
    (await apiClient.delete<{ status: string }>(`/api/characters/${characterId}`)).data,

  extendCharacter: async (characterId: string) =>
    (await apiClient.post<CharacterCard>(`/api/characters/${characterId}/extend`, {})).data,

  simulateCharacter: async (characterId: string, context: Record<string, unknown>) =>
    (await apiClient.post<Record<string, unknown>>(`/api/characters/${characterId}/simulate`, { context })).data,

  listCharacterMemories: async (characterId: string) =>
    (await apiClient.get<CharacterMemory[]>(`/api/characters/${characterId}/memories`)).data,

  listContentVersions: async (chapterId: string) =>
    (await apiClient.get<ContentVersion[]>(`/api/chapters/${chapterId}/content-versions`)).data,

  activateContentVersion: async (chapterId: string, versionId: string) =>
    (await apiClient.post(`/api/chapters/${chapterId}/content-versions/${versionId}/activate`, {})).data,

  listDhoCandidates: async (projectId: string) =>
    (await apiClient.get<DhoCandidate[]>(`/api/projects/${projectId}/outline/replan-candidates`)).data,

  createDhoCandidate: async (
    projectId: string,
    payload: { affected_from: number; trigger: Record<string, unknown> },
  ) => (await apiClient.post<DhoCandidate>(`/api/projects/${projectId}/outline/replan`, payload)).data,

  decideDhoCandidate: async (projectId: string, candidateId: string, action: 'approve' | 'reject') =>
    (await apiClient.post(
      `/api/projects/${projectId}/outline/replan-candidates/${candidateId}/${action}`,
      {},
    )).data,

  listStyleVersions: async (projectId: string) =>
    (await apiClient.get<StyleVersion[]>(`/api/projects/${projectId}/style-versions`)).data,

  createStyleVersion: async (projectId: string, sample: string) =>
    (await apiClient.post<StyleVersion>(`/api/projects/${projectId}/style-versions`, { sample })).data,

  activateStyleVersion: async (projectId: string, versionId: string) =>
    (await apiClient.post(`/api/projects/${projectId}/style-versions/${versionId}/activate`, {})).data,
}
