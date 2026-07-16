import { useEffect, useState } from 'react';

interface StreamingTextProps {
  content: string;
  className?: string;
}

export function StreamingText({ content, className = '' }: StreamingTextProps) {
  const [cursorVisible, setCursorVisible] = useState(true);

  // 闪烁光标效果
  useEffect(() => {
    const interval = setInterval(() => {
      setCursorVisible((v) => !v);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  if (!content) {
    return (
      <p className={`text-sm text-paper-300/35 ${className}`}>正文将在这里逐字浮现…</p>
    );
  }

  return (
    <div className={`manuscript whitespace-pre-wrap ${className}`}>
      {content}
      <span
        className={`ml-0.5 inline-block h-5 w-[3px] translate-y-0.5 rounded-full bg-cinnabar-500 align-middle transition-opacity ${
          cursorVisible ? 'opacity-100' : 'opacity-0'
        }`}
        aria-hidden="true"
      />
    </div>
  );
}
