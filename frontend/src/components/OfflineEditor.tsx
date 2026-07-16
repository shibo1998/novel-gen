import { useState } from 'react';

interface OfflineEditorProps {
  initialContent: string;
  onSave: (content: string) => void;
  disabled?: boolean;
  className?: string;
}

export function OfflineEditor({
  initialContent,
  onSave,
  disabled = false,
  className = '',
}: OfflineEditorProps) {
  const [content, setContent] = useState(initialContent);
  const [isDirty, setIsDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setContent(e.target.value);
    setIsDirty(true);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave(content);
      setIsDirty(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Ctrl/Cmd + S 保存
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      if (!disabled && isDirty) {
        handleSave();
      }
    }
  };

  return (
    <div className={`relative ${className}`}>
      <textarea
        value={content}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        className="manuscript min-h-[24rem] w-full resize-y rounded-md border border-ink-600 bg-ink-950/40 p-5 outline-none transition placeholder:text-paper-300/30 focus:border-cinnabar-500/60 focus:ring-2 focus:ring-cinnabar-500/15 disabled:opacity-50"
        placeholder="开始写作…（Ctrl / ⌘ + S 保存）"
      />

      {/* 状态栏 */}
      <div className="pointer-events-none absolute bottom-3 right-4 flex items-center gap-3 text-xs text-paper-300/40">
        {isDirty && <span className="text-gold-300">● 未保存</span>}
        <span>{content.length} 字符</span>
        <span>约 {Math.ceil(content.length / 2)} 字</span>
        {isSaving && <span className="text-cinnabar-300">保存中…</span>}
      </div>

      {/* 保存按钮 */}
      {isDirty && !disabled && (
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="primary-button absolute right-3 top-3 min-h-0 px-3 py-1.5 text-xs"
        >
          {isSaving ? '保存中…' : '保存'}
        </button>
      )}
    </div>
  );
}
