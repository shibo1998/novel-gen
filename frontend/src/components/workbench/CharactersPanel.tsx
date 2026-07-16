import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { MessageSquare, Plus, Save, Sparkles, Trash2 } from 'lucide-react'
import { workbenchApi } from '@/api/workbench'
import type { CharacterCard, CharacterMemory, CharacterProfile } from '@/types/workbench'

const emptyProfile = (): CharacterProfile => ({
  action_beats: [],
  speech_profile: {
    avg_sentence_length: 12,
    question_frequency: 'medium',
    rhetorical_questions: false,
    trailing_thoughts: false,
    signature_patterns: [],
  },
})

export function CharactersPanel({ projectId }: { projectId: string }) {
  const [characters, setCharacters] = useState<CharacterCard[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [description, setDescription] = useState('')
  const [memories, setMemories] = useState<CharacterMemory[]>([])
  const [context, setContext] = useState('')
  const [simulation, setSimulation] = useState('')
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const selected = useMemo(
    () => characters.find((character) => character.id === selectedId) || null,
    [characters, selectedId],
  )

  const load = useCallback(async () => {
    try {
      const result = await workbenchApi.listCharacters(projectId)
      setCharacters(result)
      setSelectedId((current) => current && result.some((item) => item.id === current) ? current : result[0]?.id || null)
      setError(null)
    } catch { setError('无法读取角色卡') }
  }, [projectId])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (!selected) { setDescription(''); setMemories([]); return }
    setDescription(selected.description || '')
    void workbenchApi.listCharacterMemories(selected.id).then(setMemories).catch(() => setMemories([]))
  }, [selected])

  const create = async (event: FormEvent) => {
    event.preventDefault()
    if (!newName.trim()) return
    setBusy('create')
    try {
      const character = await workbenchApi.createCharacter(projectId, {
        name: newName.trim(), display_name: newName.trim(), description: '', profile: emptyProfile(),
      })
      setNewName(''); setCreating(false); await load(); setSelectedId(character.id)
    } catch { setError('角色创建失败，名称可能已存在') }
    finally { setBusy(null) }
  }

  const save = async () => {
    if (!selected) return
    setBusy('save')
    try {
      const updated = await workbenchApi.updateCharacter(selected.id, {
        description,
        profile: selected.profile,
        chapter_applied: 0,
        change_summary: 'Workbench character edit',
      })
      setCharacters((items) => items.map((item) => item.id === updated.id ? updated : item))
    } catch { setError('角色保存失败') }
    finally { setBusy(null) }
  }

  const extend = async () => {
    if (!selected) return
    setBusy('extend')
    try { await workbenchApi.extendCharacter(selected.id); await load() }
    catch { setError('AI 扩展失败或返回的角色卡格式无效') }
    finally { setBusy(null) }
  }

  const simulate = async () => {
    if (!selected || !context.trim()) return
    setBusy('simulate')
    try {
      const result = await workbenchApi.simulateCharacter(selected.id, { scene_summary: context.trim() })
      setSimulation(String(result.response || JSON.stringify(result, null, 2)))
    } catch { setError('角色对白模拟失败') }
    finally { setBusy(null) }
  }

  const remove = async () => {
    if (!selected || !window.confirm(`停用角色“${selected.display_name}”？`)) return
    setBusy('delete')
    try { await workbenchApi.deleteCharacter(selected.id); await load() }
    catch { setError('角色停用失败') }
    finally { setBusy(null) }
  }

  return (
    <section aria-labelledby="characters-heading" className="space-y-4">
      <div className="flex items-center justify-between"><div><h2 id="characters-heading" className="text-base font-semibold text-paper-50">角色工作室</h2><p className="mt-1 text-sm text-paper-300/45">角色卡版本、说话指纹和已确认章节记忆。</p></div><button type="button" onClick={() => setCreating((value) => !value)} className="action-button"><Plus size={15} />新建角色</button></div>
      {creating && <form onSubmit={(event) => void create(event)} className="flex gap-2 border-y border-ink-700 py-3"><label className="sr-only" htmlFor="new-character">角色名</label><input id="new-character" className="field-input flex-1" value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="角色名" /><button className="primary-button" disabled={!newName.trim() || busy !== null}>创建</button></form>}
      {error && <p role="alert" className="alert-error">{error}</p>}
      <div className="grid min-h-[28rem] gap-0 border-y border-ink-700 md:grid-cols-[13rem_1fr]">
        <nav aria-label="角色列表" className="border-b border-ink-700 py-3 md:border-b-0 md:border-r md:border-ink-700/60 md:pr-3">
          {characters.length === 0 ? <p className="px-2 text-sm text-paper-300/40">暂无角色</p> : characters.map((character) => <button type="button" key={character.id} onClick={() => setSelectedId(character.id)} className={`list-nav-item ${selectedId === character.id ? 'list-nav-item-active' : ''}`}><span className="font-medium">{character.display_name}</span><span className="text-xs text-paper-300/40">{character.current_version_id ? '已版本化' : '未版本化'}</span></button>)}
        </nav>
        {selected ? <div className="space-y-5 py-4 md:pl-5">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-serif text-lg font-semibold text-paper-100">{selected.display_name}</h3><p className="mono-id">{selected.name}</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void remove()} disabled={busy !== null} className="secondary-button" title="停用角色"><Trash2 size={15} /><span className="sr-only">停用角色</span></button><button type="button" onClick={() => void extend()} disabled={busy !== null} className="secondary-button"><Sparkles size={15} />AI 扩展</button><button type="button" onClick={() => void save()} disabled={busy !== null} className="action-button"><Save size={15} />保存</button></div></div>
          <label className="field-label">角色描述<textarea className="field-textarea min-h-24" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <div className="grid gap-4 lg:grid-cols-2"><div><h4 className="section-label">动作节拍</h4>{selected.profile.action_beats.length ? <ul className="plain-list">{selected.profile.action_beats.map((beat) => <li key={beat}>{beat}</li>)}</ul> : <p className="text-sm text-paper-300/40">尚未配置，使用 AI 扩展补齐。</p>}</div><div><h4 className="section-label">说话指纹</h4><dl className="compact-definition"><div><dt>平均句长</dt><dd>{selected.profile.speech_profile.avg_sentence_length}</dd></div><div><dt>提问频率</dt><dd>{selected.profile.speech_profile.question_frequency}</dd></div><div><dt>习惯留半句</dt><dd>{selected.profile.speech_profile.trailing_thoughts ? '是' : '否'}</dd></div></dl></div></div>
          <div className="grid gap-4 lg:grid-cols-2"><div><h4 className="section-label">对白模拟</h4><textarea className="field-textarea min-h-20" value={context} onChange={(event) => setContext(event.target.value)} placeholder="输入当前场景" /><button type="button" onClick={() => void simulate()} disabled={!context.trim() || busy !== null} className="action-button mt-2"><MessageSquare size={15} />模拟回应</button>{simulation && <pre className="result-block mt-2">{simulation}</pre>}</div><div><h4 className="section-label">记忆时间线</h4>{memories.length ? <ol className="timeline">{memories.map((memory) => <li key={memory.id}><span>第 {memory.chapter_number ?? '?'} 章</span><p>{memory.summary || memory.content}</p></li>)}</ol> : <p className="text-sm text-paper-300/40">已确认章节尚未形成该角色的记忆。</p>}</div></div>
        </div> : <p className="empty-state m-4">选择或创建角色</p>}
      </div>
    </section>
  )
}
