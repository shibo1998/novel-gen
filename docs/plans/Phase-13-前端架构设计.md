# Phase 13：前端架构设计

> **定位**：前端状态管理 + 路由 + 组件分层设计。本文档是**架构蓝图**，非实现代码。
> 前端开发者可直接参考本架构进行开发。

---

## 一、技术选型

| 层 | 推荐 | 理由 |
|----|------|------|
| 框架 | React 18+ / Next.js 14 | 生态完善，流式渲染支持好 |
| 状态管理 | Zustand | 轻量，TypeScript 友好，比 Redux 少 90% 样板代码 |
| 编辑器 | TipTap（基于 ProseMirror） | 支持协同编辑 + 自定义插件 + 只读/编辑模式切换 |
| 图表 | Recharts / D3 | 仪表盘 + 角色关系图 |
| SSE | 原生 EventSource + fetch 流式 | 写作进度实时推送 |
| 样式 | Tailwind CSS | 快速迭代 |
| 路由 | Next.js App Router | 文件系统路由 + Server Components |

---

## 二、状态管理架构

```typescript
// zustand stores

// ── 项目全局状态 ──
interface ProjectStore {
  currentProject: Project | null;
  volumeTree: { volumes: Volume[]; chapters: Chapter[] };
  selectedNode: { type: 'volume' | 'chapter' | 'scene'; id: string } | null;
  // actions
  selectChapter: (id: string) => void;
  reorderChapter: (chapterId: string, newIndex: number) => void;
  addVolume: () => void;
}

// ── 写作状态 ──
interface WritingStore {
  draftContent: string;
  streamStatus: 'idle' | 'streaming' | 'done' | 'error';
  streamBuffer: string;
  generationProgress: { currentEvent: number; totalEvents: number };
  lastSaved: Date | null;
  // actions
  startGeneration: (params: GenerationParams) => Promise<void>;
  appendChunk: (chunk: string) => void;
  applyDraft: () => void;
  saveContent: () => Promise<void>;
}

// ── 角色管理 ──
interface CharacterStore {
  characters: Map<string, CharacterProfile>;
  selectedCharacterId: string | null;
  editingField: string | null;  // 当前正在编辑的字段
  // actions
  updateCharacter: (id: string, updates: Partial<CharacterProfile>) => void;
}

// ── 审校状态 ──
interface ReviewStore {
  issues: ReviewIssue[];
  selectedIssueId: string | null;
  filterStatus: 'all' | 'major' | 'minor';
  // actions
  filterIssues: (status: FilterStatus) => void;
  acceptFix: (issueId: string) => void;
  rejectFix: (issueId: string) => void;
}
```

---

## 三、路由设计

| 路由 | 页面 | 描述 |
|------|------|------|
| `/projects` | 项目列表 | 创建/管理项目 |
| `/projects/:id` | 项目详情 | 大纲总览、角色/世界观管理 |
| `/write/:projectId/:chapterId` | **写作工作台** | 核心页面 |
| `/admin/metrics` | 可观测性仪表盘 | Phase 12 数据可视化 |
| `/admin/bible/:projectId` | Bible 演化时间线 | Phase 11 可视化 |

### 写作工作台布局

```
┌─────────────┬──────────────────────────────┬────────────────┐
│  大纲导航    │       写作区                 │   辅助面板     │
│  (Outline)  │   (WritingWorkspace)         │   (侧边栏)    │
│             │                              │               │
│  卷/章/事件  │  工具栏：生成/重写/审校/保存  │  [角色卡]     │
│  树状结构    │  ─────────────────────────  │  [约束卡]     │
│  可拖拽     │  TipTap 编辑器               │  [审校报告]   │
│  可点击跳转  │  （流式输出实时追加）          │               │
│             │  ─────────────────────────  │               │
│             │  底部：字数/进度/保存时间     │               │
└─────────────┴──────────────────────────────┴───────────────┘
```

---

## 四、SSE 流式生成 Hook

```typescript
// frontend/src/hooks/useStreamGeneration.ts

export function useStreamGeneration(projectId: string, chapterId: string) {
  const store = useWritingStore();

  const startGeneration = async (params: GenerationParams) => {
    store.setStreamStatus('streaming');

    const response = await fetch(`/api/v1/write/${projectId}/${chapterId}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n').filter(l => l.startsWith('data: '));

      for (const line of lines) {
        const data = JSON.parse(line.slice(6));
        switch (data.type) {
          case 'text':
            store.appendChunk(data.content);  // 实时追加到编辑器
            break;
          case 'progress':
            store.setProgress(data.current, data.total);
            break;
          case 'done':
            store.setStreamStatus('done');
            break;
          case 'error':
            store.setStreamStatus('error');
            store.setError(data.message);
            break;
        }
      }
    }
  };

  return { startGeneration, status: store.streamStatus, draft: store.draftContent };
}
```

---

## 五、角色关系图谱

```tsx
// frontend/src/components/CharacterGraph.tsx

// 用 D3 force layout 或 Recharts 展示角色关系网
// 数据来源：GET /api/v1/bible/:projectId/relationships?chapter=50

interface GraphData {
  nodes: Array<{ id: string; name: string; appearances: number; faction: string }>;
  edges: Array<{ source: string; target: string; type: 'ally' | 'enemy' | 'romantic' | 'mentor'; weight: number }>;
}

// 节点 = 角色（大小 ∝ 出场次数，颜色 = 阵营）
// 边 = 关系（粗细 ∝ 互动频率，颜色 = 关系类型）
// 点击节点 → 右侧面板切换到该角色档案
```

---

## 六、验证清单

```
☐ Zustand stores 四个核心 Store 实现
☐ Next.js App Router 路由搭建
☐ TipTap 编辑器集成（基础编辑 + 流式追加）
☐ 三栏布局写作工作台
☐ SSE 流式生成 Hook + 进度条
☐ 大纲树组件（可折叠卷/章，可点击跳转）
☐ 审校报告面板（列表 + 点击定位到正文对应位置）
☐ 角色关系图谱组件（Phase 11 Bible 数据可视化）
☐ /admin/metrics 仪表盘（Phase 12 数据展示）
```

---

## 七、API 对接参考

| 前端需求 | 后端 API | 数据格式 |
|---------|---------|---------|
| 获取项目列表 | `GET /api/projects` | `Project[]` |
| 获取章节正文 | `GET /api/chapters/:id` | `Chapter` |
| 流式生成 | `POST /api/v1/write/:id/stream` | SSE |
| 角色 Bible 快照 | `GET /api/bible/:projectId/snapshot?chapter=N` | Phase 11 |
| 指标总览 | `GET /api/admin/metrics/summary?project_id=X` | Phase 12 |
| 质量报告 | `GET /api/admin/metrics/chapter-cost?project_id=X&chapter=N` | Phase 14 |
