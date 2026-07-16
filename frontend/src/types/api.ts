export interface ApiResponse<T> {
  data: T
  message?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ApiError {
  code: string
  message: string
  details?: unknown
}

type GeneratedTaskStatus = components['schemas']['TaskStatus']

// 任务状态：基础字段来自 OpenAPI，只收窄运行时状态与扩展元数据。
export type TaskStatus = Omit<GeneratedTaskStatus, 'status' | 'result' | 'meta'> & {
  status: 'pending' | 'running' | 'completed' | 'failed' | 'orphaned' | 'interrupted'
  result?: unknown
  meta?: {
    phase?: string
    message?: string
    active_volume?: number
    batch_start?: number
    batch_end?: number
    completed_chapter_count?: number
    target_chapter_count?: number
  }
}

// 世界观
export interface WorldbuildingResult {
  setting_document: string
  constraints: {
    hard: string[]
    soft: string[]
  }
  conflict_seeds: Array<{
    name: string
    description: string
    stake: string
  }>
}

// 卷状态
export type VolumeStatusValue = 'planned' | 'planning' | 'detailed' | 'writing' | 'completed' | 'archived'

export interface VolumeContract {
  opening_state?: string
  ending_state?: string
  handoff_hook?: string
  must_resolve?: string[]
}

export interface VolumeStatus {
  id: string
  project_id: string
  volume_number: number
  title: string | null
  core_conflict: string | null
  character_arc_stage: string | null
  status: VolumeStatusValue
  chapter_start: number | null
  chapter_end: number | null
  summary: string | null
  contract: VolumeContract
  planned_chapter_count: number
  target_chapter_count: number
  is_complete: boolean
}

// 大纲
export interface OutlineResult {
  volumes: Array<{
    number: number
    title: string
    core_conflict: string
    character_arc_stage: string
    status: VolumeStatusValue
    chapter_start: number | null
    chapter_end: number | null
    summary: string | null
    contract: VolumeContract
    planned_chapter_count: number
    target_chapter_count: number
    is_complete: boolean
    has_detail: boolean
  }>
  chapters: Array<{
    volume: number
    number: number
    title: string
    goal: string
    key_events: Array<{ event_name: string; brief: string }>
    pov_character: string
    foreshadowing_seeds: Array<{ name: string; brief: string }>
  }>
  foreshadowing_registry: Array<{
    name: string
    description: string
    sow_chapter: number | null
    reap_chapter: number | null
  }>
}
import type { components } from './generated'
