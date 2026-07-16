import { useEffect, useState } from 'react';

interface OfflineIndicatorProps {
  className?: string;
}

export function OfflineIndicator({ className = '' }: OfflineIndicatorProps) {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [wasOffline, setWasOffline] = useState(false);
  const [showReconnected, setShowReconnected] = useState(false);

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      if (wasOffline) {
        setShowReconnected(true);
        setTimeout(() => setShowReconnected(false), 3000);
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

  if (!isOnline) {
    return (
      <div className={`fixed bottom-5 left-5 z-[100] flex items-center gap-2 rounded-lg border border-gold-500/40 border-l-2 border-l-gold-500 bg-ink-800/95 px-3.5 py-2.5 text-sm text-gold-300 shadow-lift backdrop-blur-sm animate-toast-in ${className}`}>
        <span className="h-2 w-2 animate-ink-pulse rounded-full bg-gold-400" />
        离线模式 · 内容将自动保存
      </div>
    );
  }

  if (showReconnected) {
    return (
      <div className={`fixed bottom-5 left-5 z-[100] flex items-center gap-2 rounded-lg border border-jade-500/40 border-l-2 border-l-jade-500 bg-ink-800/95 px-3.5 py-2.5 text-sm text-jade-400 shadow-lift backdrop-blur-sm animate-toast-in ${className}`}>
        <span className="h-2 w-2 rounded-full bg-jade-400" />
        已恢复在线
      </div>
    );
  }

  return null;
}
