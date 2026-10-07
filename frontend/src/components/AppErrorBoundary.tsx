import { Component, type ReactNode } from 'react'
import { ErrorPage } from '../pages/ErrorPage'

export class AppErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  render() {
    return this.state.hasError ? <ErrorPage /> : this.props.children
  }
}