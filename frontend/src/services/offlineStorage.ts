import { authorizedFetch } from '@/api/http';

const STORAGE_PREFIX = 'novel_gen_offline:';
const OFFLINE_ITEMS_KEY = 'novel_gen_offline_items';

export interface OfflineItem {
  id: string;
  type: 'scene' | 'chapter' | 'outline';
  data: unknown;
  timestamp: number;
  synced: boolean;
}

class OfflineStorage {
  save(id: string, type: OfflineItem['type'], data: unknown): void {
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
      scene: `/api/v1/scenes/${item.id}/save`,
      chapter: `/api/projects/chapters/${item.id}`,
      outline: `/api/projects/outline`,
    };
    const response = await authorizedFetch(endpoints[item.type], {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(item.data),
    });
    if (!response.ok) throw new Error(`Sync failed with HTTP ${response.status}`);
  }

  clear(): void {
    localStorage.removeItem(OFFLINE_ITEMS_KEY);
    const keys = Object.keys(localStorage).filter(k => k.startsWith(STORAGE_PREFIX));
    keys.forEach(k => localStorage.removeItem(k));
  }
}

export const offlineStorage = new OfflineStorage();
