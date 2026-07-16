import { useCallback, useRef } from 'react';
import { streamFetch, tokenStorage } from '@/api/http';
import { offlineStorage } from '@/services/offlineStorage';
import { useGenerationStore } from '@/stores/generationStore';

export interface StreamEvent {
  type: 'token' | 'progress' | 'done' | 'error' | 'resume' | 'recovering';
  content?: string;
  offset?: number;
  total_tokens?: number;
  word_count?: number;
  message?: string;
}

export interface UseStreamingWriteOptions {
  sceneId: string;
  onToken?: (token: string) => void;
  onDone?: (content: string, stats: { total_tokens: number; word_count: number }) => void;
  onError?: (error: Error) => void;
}

export function useStreamingWrite(options: UseStreamingWriteOptions) {
  const { sceneId, onToken, onDone, onError } = options;
  const streamStatus = useGenerationStore((state) => state.streamStatus);
  const content = useGenerationStore((state) => state.streamBuffer);
  const errorMessage = useGenerationStore((state) => state.error);
  const begin = useGenerationStore((state) => state.begin);
  const beginRecovery = useGenerationStore((state) => state.beginRecovery);
  const appendToken = useGenerationStore((state) => state.appendToken);
  const complete = useGenerationStore((state) => state.complete);
  const fail = useGenerationStore((state) => state.fail);
  const stop = useGenerationStore((state) => state.stop);
  const abortControllerRef = useRef<AbortController | null>(null);

  const startWriting = useCallback(async (offset: number = 0) => {
    if (offset > 0) beginRecovery(sceneId);
    else begin(sceneId);
    let accumulated = '';
    let pending = '';
    let completed = false;

    try {
      const token = tokenStorage.get();
      if (!token) {
        throw new Error('Not authenticated');
      }

      abortControllerRef.current = new AbortController();

      const response = await streamFetch(
        `/api/v1/scenes/${sceneId}/write`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ last_received_offset: offset }),
          signal: abortControllerRef.current.signal,
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        pending += decoder.decode(value, { stream: true });
        const lines = pending.split('\n');
        pending = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: StreamEvent = JSON.parse(line.slice(6));
              
              if (event.type === 'token' && event.content) {
                accumulated += event.content;
                appendToken(event.content);
                onToken?.(event.content);
              } else if (event.type === 'recovering') {
                accumulated = '';
                beginRecovery(sceneId);
              } else if (event.type === 'resume') {
                accumulated = event.content || '';
                begin(sceneId, accumulated);
              } else if (event.type === 'progress') {
                // 可以用于显示进度
              } else if (event.type === 'done') {
                completed = true;
                complete();
                onDone?.(accumulated, {
                  total_tokens: event.total_tokens || 0,
                  word_count: event.word_count || 0,
                });
                // 保存到本地
                offlineStorage.save(sceneId, 'scene', { content: accumulated });
              } else if (event.type === 'error') {
                const message = event.message || 'Unknown error';
                fail(message);
                onError?.(new Error(message));
              }
            } catch {
              // 忽略解析错误
            }
          }
        }
      }

      if (completed) offlineStorage.markSynced(sceneId, 'scene');
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Unknown error');
      if (err.name !== 'AbortError') {
        fail(err.message);
        onError?.(err);
        // 保存到本地
        offlineStorage.save(sceneId, 'scene', { content: accumulated });
      }
    }
  }, [appendToken, begin, beginRecovery, complete, fail, sceneId, onToken, onDone, onError]);

  const stopWriting = useCallback(() => {
    abortControllerRef.current?.abort();
    stop();
  }, [stop]);

  return {
    isStreaming: streamStatus === 'streaming' || streamStatus === 'recovering',
    isRecovering: streamStatus === 'recovering',
    content,
    error: errorMessage ? new Error(errorMessage) : null,
    startWriting,
    stopWriting,
  };
}
