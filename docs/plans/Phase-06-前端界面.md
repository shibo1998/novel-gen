# Phase 6：前端界面

> **本 Phase 包含**：SSE流式Hook、离线编辑器、错误处理

## 交付物

```
frontend/src/
    api/
        client.ts              # [修改] Axios实例 + 认证
        streaming.ts          # [修改] SSE处理
    hooks/
        useStreamingWrite.ts  # [修改] Fetch Stream + 断点续传
        useOfflineStorage.ts   # [新增] 离线存储
    services/
        offlineStorage.ts     # [新增] 离线存储服务
    components/
        OfflineEditor.tsx     # [新增] 离线编辑器
        StreamingText.tsx     # [新增] 流式文本展示
    pages/
        Dashboard.tsx
        ProjectSetup/WorldBuilding.tsx
        CharacterStudio/
        OutlineView/
        WritingSession/
        ReviewDashboard/
    stores/
        projectStore.ts
        writingStore.ts
        characterStore.ts
```

## 前端技术要点

### 1. Axios配置 + 认证 `frontend/src/api/client.ts`

```typescript
import axios from 'axios';

const getToken = () => localStorage.getItem('access_token');

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
});

// 请求拦截器：添加Token
client.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器：处理401
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Token过期，清除并跳转登录
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default client;
export { getToken };
```

### 2. 离线存储服务 `frontend/src/services/offlineStorage.ts`

```typescript
const STORAGE_PREFIX = 'novel_gen_offline:';
const OFFLINE_ITEMS_KEY = 'novel_gen_offline_items';

interface OfflineItem {
  id: string;
  type: 'scene' | 'chapter' | 'outline';
  data: any;
  timestamp: number;
  synced: boolean;
}

class OfflineStorage {
  save(id: string, type: OfflineItem['type'], data: any): void {
    const item: OfflineItem = {
      id,
      type,
      data,
      timestamp: Date.now(),
      synced: false,
    };
    localStorage.setItem(`${STORAGE_PREFIX}${type}:${id}`, JSON.stringify(item));
    this._updateIndex(id, type);
  }

  load<T>(id: string, type: OfflineItem['type']): T | null {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${type}:${id}`);
    if (raw) {
      const item: OfflineItem = JSON.parse(raw);
      return item.data as T;
    }
    return null;
  }

  markSynced(id: string, type: OfflineItem['type']): void {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${type}:${id}`);
    if (raw) {
      const item: OfflineItem = JSON.parse(raw);
      item.synced = true;
      localStorage.setItem(`${STORAGE_PREFIX}${type}:${id}`, JSON.stringify(item));
    }
  }

  getUnsynced(): OfflineItem[] {
    const items: OfflineItem[] = [];
    const indexRaw = localStorage.getItem(OFFLINE_ITEMS_KEY);
    if (!indexRaw) return items;
    const index: string[] = JSON.parse(indexRaw);
    for (const key of index) {
      const raw = localStorage.getItem(`${STORAGE_PREFIX}${key}`);
      if (raw) {
        const item: OfflineItem = JSON.parse(raw);
        if (!item.synced) items.push(item);
      }
    }
    return items;
  }

  async syncAll(): Promise<{ success: number; failed: number }> {
    const unsynced = this.getUnsynced();
    let success = 0, failed = 0;
    for (const item of unsynced) {
      try {
        await this._pushToServer(item);
        this.markSynced(item.id, item.type);
        success++;
      } catch {
        failed++;
      }
    }
    return { success, failed };
  }

  private _updateIndex(id: string, type: string): void {
    const indexRaw = localStorage.getItem(OFFLINE_ITEMS_KEY);
    const index: string[] = indexRaw ? JSON.parse(indexRaw) : [];
    const key = `${type}:${id}`;
    if (!index.includes(key)) {
      index.push(key);
      localStorage.setItem(OFFLINE_ITEMS_KEY, JSON.stringify(index));
    }
  }

  private async _pushToServer(item: OfflineItem): Promise<void> {
    const endpoints: Record<string, string> = {
      scene: `/scenes/${item.id}/content`,
      chapter: `/chapters/${item.id}`,
      outline: `/projects/${item.id}/outline`,
    };
    await fetch(`/api/v1${endpoints[item.type]}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      },
      body: JSON.stringify(item.data),
    });
  }
}

export const offlineStorage = new OfflineStorage();
```

### 3. 网络状态监听 `frontend/src/hooks/useNetworkStatus.ts`

```typescript
import { useState, useEffect } from 'react';

export function useNetworkStatus() {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [wasOffline, setWasOffline] = useState(false);

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      if (wasOffline) {
        // 从离线恢复，自动同步
        offlineStorage.syncAll().then(result => {
          console.log(`Synced ${result.success} items, ${result.failed} failed`);
        });
      }
    };

    const handleOffline = () => {
      setIsOnline(false);
      setWasOffline(true);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [wasOffline]);

  return { isOnline, wasOffline };
}
```

### 4. SSE流式Hook `frontend/src/hooks/useStreamingWrite.ts`

```typescript
import { useState, useCallback, useRef, useEffect } from 'react';
import { getToken } from '../api/client';

type StreamStatus = 'idle' | 'streaming' | 'paused' | 'error' | 'done';

interface StreamMessage {
  type: 'resume' | 'progress' | 'token' | 'done' | 'error';
  content?: string;
  offset?: number;
  total_tokens?: number;
  message?: string;
}

export function useStreamingWrite(sceneId: string) {
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [content, setContent] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState({ tokens: 0 });
  const [lastOffset, setLastOffset] = useState(0);

  const abortControllerRef = useRef<AbortController | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const start = useCallback(async () => {
    setStatus('streaming');
    setError(null);
    abortControllerRef.current = new AbortController();

    try {
      // 尝试从localStorage恢复检查点
      const savedCheckpoint = localStorage.getItem(`scene_${sceneId}_checkpoint`);
      let offset = 0;
      if (savedCheckpoint) {
        const cp = JSON.parse(savedCheckpoint);
        offset = cp.offset || 0;
        setContent(cp.content || '');
        setLastOffset(offset);
      }

      const response = await fetch(`/api/v1/scenes/${sceneId}/write`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify({ last_received_offset: offset }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const msg: StreamMessage = JSON.parse(line.slice(6));
            handleMessage(msg);
          } catch {
            console.warn('Failed to parse SSE message');
          }
        }
      }
    } catch (e) {
      if (e.name === 'AbortError') {
        setStatus('paused');
        // 保存检查点
        localStorage.setItem(`scene_${sceneId}_checkpoint`, JSON.stringify({
          content,
          offset: lastOffset + progress.tokens
        }));
      } else {
        setStatus('error');
        setError(e.message);
        // 3秒后自动重连
        reconnectTimeoutRef.current = setTimeout(() => start(), 3000);
      }
    }
  }, [sceneId, lastOffset, content, progress.tokens]);

  const handleMessage = (msg: StreamMessage) => {
    switch (msg.type) {
      case 'resume':
        setContent(msg.content || '');
        setLastOffset(msg.offset || 0);
        break;
      case 'progress':
        setProgress({ tokens: msg.offset || 0 });
        break;
      case 'token':
        setContent(prev => prev + (msg.content || ''));
        break;
      case 'done':
        setStatus('done');
        setLastOffset(0);
        localStorage.removeItem(`scene_${sceneId}_checkpoint`);
        break;
      case 'error':
        setStatus('error');
        setError(msg.message || 'Unknown error');
        break;
    }
  };

  const pause = useCallback(() => {
    abortControllerRef.current?.abort();
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    setStatus('paused');
  }, []);

  const resume = useCallback(() => {
    start();
  }, [start]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  return {
    status,
    content,
    error,
    progress,
    start,
    pause,
    resume,
    lastOffset,
  };
}
```

### 5. 离线编辑器组件 `frontend/src/components/OfflineEditor.tsx`

```typescript
import { useState, useEffect, useCallback } from 'react';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { offlineStorage } from '../services/offlineStorage';

interface OfflineEditorProps {
  sceneId: string;
  initialContent: string;
  onSave: (content: string) => Promise<void>;
}

export function OfflineEditor({ sceneId, initialContent, onSave }: OfflineEditorProps) {
  const [content, setContent] = useState(initialContent);
  const [isSaving, setIsSaving] = useState(false);
  const [syncStatus, setSyncStatus] = useState<'synced' | 'pending' | 'offline'>('synced');
  const { isOnline } = useNetworkStatus();

  // 加载离线内容
  useEffect(() => {
    const offline = offlineStorage.load<{ content: string }>(sceneId, 'scene');
    if (offline && offline.content !== initialContent) {
      setContent(offline.content);
      setSyncStatus('pending');
    }
  }, [sceneId, initialContent]);

  const handleChange = useCallback((newContent: string) => {
    setContent(newContent);
    // 实时保存到localStorage
    offlineStorage.save(sceneId, 'scene', { content: newContent });
    setSyncStatus('pending');
  }, [sceneId]);

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    try {
      if (isOnline) {
        await onSave(content);
        offlineStorage.markSynced(sceneId, 'scene');
        setSyncStatus('synced');
      } else {
        offlineStorage.save(sceneId, 'scene', { content });
        setSyncStatus('offline');
        alert('内容已保存到本地，网络恢复后将自动同步');
      }
    } catch (e) {
      // 保存失败也存本地
      offlineStorage.save(sceneId, 'scene', { content });
      setSyncStatus('offline');
    } finally {
      setIsSaving(false);
    }
  }, [content, isOnline, sceneId, onSave]);

  return (
    <div className="offline-editor">
      {/* 状态栏 */}
      <div className="flex items-center gap-2 text-sm">
        {!isOnline && (
          <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded">
            离线模式
          </span>
        )}
        {syncStatus === 'pending' && isOnline && (
          <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded">
            有未同步的更改
          </span>
        )}
        {syncStatus === 'offline' && (
          <span className="px-2 py-1 bg-orange-100 text-orange-800 rounded">
            待同步到服务器
          </span>
        )}
      </div>

      {/* 编辑器 */}
      <textarea
        value={content}
        onChange={(e) => handleChange(e.target.value)}
        className="w-full h-96 p-4 border rounded-lg"
        placeholder={isOnline ? "开始写作..." : "离线模式 - 内容将在恢复网络后保存"}
        disabled={!isOnline && syncStatus === 'synced'}
      />

      {/* 保存按钮 */}
      <button
        onClick={handleSave}
        disabled={isSaving}
        className="px-4 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50"
      >
        {isSaving ? '保存中...' : '保存'}
      </button>
    </div>
  );
}
```

### 6. 写作会话页面 `frontend/src/pages/WritingSession/WritingPage.tsx`

```typescript
import { useStreamingWrite } from '../../hooks/useStreamingWrite';
import { OfflineEditor } from '../../components/OfflineEditor';
import { StreamingText } from '../../components/StreamingText';
import client from '../../api/client';

interface Props {
  sceneId: string;
}

export function WritingPage({ sceneId }: Props) {
  const { status, content, error, progress, start, pause, resume } = useStreamingWrite(sceneId);
  const [confirmedContent, setConfirmedContent] = useState('');

  // 开始生成
  const handleStartGeneration = () => {
    start();
  };

  // 确认内容
  const handleConfirm = () => {
    setConfirmedContent(content);
    // 保存到服务器
    client.put(`/scenes/${sceneId}/content`, { content });
  };

  // 重新生成
  const handleRegenerate = () => {
    setConfirmedContent('');
    start();
  };

  return (
    <div className="flex h-screen">
      {/* 左侧：约束卡 */}
      <div className="w-1/4 p-4 border-r">
        <h2 className="font-bold mb-4">约束卡</h2>
        <ConstraintCardDisplay sceneId={sceneId} />
      </div>

      {/* 中间：写作区域 */}
      <div className="flex-1 flex flex-col p-4">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold">第X章 第Y场景</h1>
          <div className="flex gap-2">
            {status === 'idle' && (
              <button onClick={handleStartGeneration} className="px-4 py-2 bg-green-600 text-white rounded">
                开始生成
              </button>
            )}
            {status === 'streaming' && (
              <button onClick={pause} className="px-4 py-2 bg-yellow-600 text-white rounded">
                暂停
              </button>
            )}
            {status === 'paused' && (
              <button onClick={resume} className="px-4 py-2 bg-blue-600 text-white rounded">
                继续
              </button>
            )}
            {(status === 'done' || status === 'paused') && content && (
              <>
                <button onClick={handleConfirm} className="px-4 py-2 bg-green-600 text-white rounded">
                  确认
                </button>
                <button onClick={handleRegenerate} className="px-4 py-2 bg-red-600 text-white rounded">
                  重新生成
                </button>
              </>
            )}
          </div>
        </div>

        {/* 进度显示 */}
        {status === 'streaming' && (
          <div className="mb-4">
            <div className="text-sm text-gray-500">生成中... {progress.tokens} tokens</div>
          </div>
        )}

        {/* 流式文本展示 */}
        <StreamingText
          content={content}
          isStreaming={status === 'streaming'}
          className="flex-1 p-4 border rounded-lg min-h-96"
        />

        {/* 错误显示 */}
        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">
            生成失败: {error}
          </div>
        )}
      </div>

      {/* 右侧：场景列表 */}
      <div className="w-1/5 p-4 border-l">
        <h2 className="font-bold mb-4">场景列表</h2>
        <SceneList chapterId={sceneId} />
      </div>
    </div>
  );
}
```

## 页面设计

### 1. Dashboard — 项目管理

- 项目卡片列表（标题、状态Badge、进度条、更新时间）
- 新建项目按钮 → 弹窗输入核心创意+类型+风格
- 点击项目 → 进入设定工坊

### 2. ProjectSetup — 设定工坊

- 左侧：核心创意输入（如果还为空）
- 中间：AI生成的设定文档（Markdown渲染，可编辑）
- 右侧：硬约束清单 + 软约束清单（tag形式，可增删）
- 底部：冲突种子列表
- 操作：保存 → 触发生成大纲

### 3. CharacterStudio — 角色工坊

- 角色卡片列表（头像、名称、标签，支持拖拽排序）
- 角色详情Tab：基础设定、心理档案、语言风格、关系网、记忆库
- 测试模拟按钮 → 弹窗：输入情境 → 实时看角色回应

### 4. OutlineView — 大纲视图

- 三列：卷列表 | 章列表 | 章详情
- 章详情：标题、叙事目标、关键事件时间线、POV角色、伏笔标记
- 支持拖拽调整章节顺序
- 伏笔注册表：表格视图，按状态筛选
- **版本对比**：显示当前版本与历史版本的差异

### 5. WritingSession — 写作会话（核心页面）

- 左上：约束卡展示（折叠面板）
- 中间：SSE流式文本区域（逐token打字效果 + 实时字数统计）
- 右下：接受 / 重新生成 / 手动编辑
- 右侧：场景列表（当前章所有场景，标记生成状态）

### 6. ReviewDashboard — 审校面板

- 上半部：正文显示，问题行高亮标记
- 下半部：问题列表（颜色标签区分severity）
- 操作：逐条接受/拒绝 → 批量确认

## 路由设计

```typescript
// frontend/src/App.tsx
const routes = [
    { path: '/', element: <Dashboard /> },
    { path: '/login', element: <LoginPage /> },
    { path: '/projects/:id/setup', element: <WorldBuilding /> },
    { path: '/projects/:id/characters', element: <CharacterStudio /> },
    { path: '/projects/:id/outline', element: <OutlineView /> },
    { path: '/projects/:id/write/:sceneId', element: <WritingPage /> },
    { path: '/projects/:id/review/:sceneId', element: <ReviewPage /> },
];
```

## 验证清单

```
基础验证：
☐ 六个页面路由正常
☐ 创建项目 → 世界观生成 → 大纲生成 流程完整
☐ 写作会话流式展示正常
☐ 审校面板能展示和操作问题列表

离线功能验证：
☐ 断开网络 → 编辑内容不丢失
☐ 恢复网络 → 自动同步
☐ 显示离线/在线状态

SSE流式验证：
☐ 前端收到tokens并实时显示
☐ 断开网络 → 内容保存到检查点
☐ 传入last_received_offset → 从断点继续
```

## 依赖关系

- **前置**：Phase 1-5.5（后端API全部就绪）
- **并行**：可以与后端开发并行进行

## 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | React 18 + TypeScript |
| 构建 | Vite |
| 样式 | TailwindCSS |
| 状态 | Zustand |
| 路由 | React Router v6 |
| HTTP | Axios |
| 图表 | Recharts（雷达图） |
| 图谱 | React Force Graph（关系可视化） |
