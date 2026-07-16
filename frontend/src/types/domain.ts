export interface User {
  id: string
  email: string
  username: string
  is_active: boolean
  created_at: string
}

export interface Project {
  id: string
  user_id?: string
  title: string
  core_idea: string
  genre?: string
  tone_style?: string
  target_word_count: number
  target_chapter_count: number
  status: string
  created_at: string
  updated_at: string
}

export interface Entity {
  id: string
  project_id: string
  type: 'character' | 'location' | 'organization' | 'item' | 'rule' | 'magic_system'
  name: string
  display_name: string
  description?: string
  data: Record<string, unknown>
  version: number
  created_at: string
  updated_at: string
}

export interface Chapter {
  id: string
  project_id: string
  volume_number: number
  chapter_number: number
  title?: string
  outline?: Record<string, unknown>
  word_count: number
  status: 'planned' | 'outlining' | 'writing' | 'reviewing' | 'completed'
  created_at: string
  updated_at: string
}

export interface Scene {
  id: string
  chapter_id: string
  project_id: string
  scene_number: number
  title?: string
  location?: string
  time_period?: string
  constraint_card?: Record<string, unknown>
  content?: string
  word_count: number
  pov_character_id?: string
  status: 'planned' | 'writing' | 'completed'
  created_at: string
  updated_at: string
}
