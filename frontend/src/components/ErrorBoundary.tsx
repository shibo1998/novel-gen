import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <main className="relative z-10 grid min-h-screen place-items-center p-6 text-paper-100">
          <div className="ink-card max-w-lg border-l-2 border-l-cinnabar-500 p-6 animate-fade-up">
            <h1 className="font-display text-lg font-semibold text-paper-50">页面出现错误</h1>
            <p className="mt-2 text-sm text-paper-300/50">请刷新页面；若问题持续，请查看浏览器控制台。</p>
          </div>
        </main>
      )
    }
    return this.props.children
  }
}
