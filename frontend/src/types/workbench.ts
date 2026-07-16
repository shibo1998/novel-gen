export interface ProjectChapter {
  id: string
  chapter_number: number
  volume_number: number
  title: string | null
  status: string
  word_count: number
  scene_count: number
  is_locked: boolean
  active_content_version_id: string | null
}

export interface ProjectTask {
  task_id: string
  scene_id: string | null
  context_snapshot_id: string | null
  task_type: string
  phase: string
  status: string
  error: string | null
  recovery_attempt_count: number
  max_recovery_attempts: number
  recovery_allowance: number
  spent_cost: number
  can_recover: boolean
  updated_at: string
  completed_at: string | null
}

export interface ReviewItem {
  id: string
  chapter_id: string
  chapter_content_version_id: string
  type: string
  priority: string
  status: string
  reason: {
    verdict?: string
    weak_spots?: Array<{ label?: string; score?: number; reason?: string }>
    evaluation_status?: string
  }
  created_at: string
}

export interface SpeechProfile {
  avg_sentence_length: number
  question_frequency: string
  rhetorical_questions: boolean
  trailing_thoughts: boolean
  signature_patterns: string[]
}

export interface CharacterProfile {
  action_beats: string[]
  speech_profile: SpeechProfile
}

export interface CharacterCard {
  id: string
  project_id: string
  name: string
  display_name: string
  description: string
  profile: CharacterProfile
  current_version_id: string | null
}

export interface CharacterMemory {
  id: string
  chapter_number: number | null
  type: string
  content: string
  summary: string | null
  salience: number
}

export interface ContentVersion {
  id: string
  version_number: number
  source: string
  change_summary: string | null
  created_at: string
  is_active: boolean
}

export interface DhoDiff {
  chapters_added: Array<Record<string, unknown> & { number: number }>
  chapters_removed: Array<Record<string, unknown> & { number: number }>
  chapters_modified: Array<{
    number: number
    old: Record<string, unknown>
    new: Record<string, unknown>
  }>
}

export interface DhoCandidate {
  id: string
  status: string
  trigger: Record<string, unknown>
  affected_from: number
  affected_to: number | null
  diff: DhoDiff
  created_at: string
}

export interface StyleVersion {
  id: string
  version_number: number
  profile: Record<string, unknown>
  active: boolean
  created_at: string
}

export interface SceneSummary {
  id: string
  chapter_id: string
  scene_number: number
  title: string | null
  content: string | null
  word_count: number
  status: string
}
