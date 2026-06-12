import { Component, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { isChunkLoadError, reloadOnceOnChunkError } from '@/lib/chunkLoadRecovery'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    if (isChunkLoadError(error)) {
      reloadOnceOnChunkError()
      return { hasError: false, error: null }
    }
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    if (isChunkLoadError(error)) {
      reloadOnceOnChunkError()
      return
    }
    console.error('ErrorBoundary caught:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback

      return (
        <div
          role="alert"
          className="flex flex-col items-center justify-center min-h-[40vh] p-8 text-center"
        >
          <AlertTriangle className="w-12 h-12 text-red-500 mb-4" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Something went wrong
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 max-w-md">
            {isChunkLoadError(this.state.error)
              ? '页面资源已更新，请刷新后继续使用。'
              : this.state.error?.message || 'An unexpected error occurred.'}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null })
              reloadOnceOnChunkError()
            }}
            className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            {isChunkLoadError(this.state.error) ? '刷新页面' : 'Reload Page'}
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
