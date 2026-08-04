import { Component, type ErrorInfo, type ReactNode } from "react";

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  error: Error | null;
}

export default class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("OfferPilot page rendering failed", error, errorInfo);
  }

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <div className="flex min-h-full items-center justify-center bg-white p-6">
        <div className="w-full max-w-lg rounded-2xl border border-error-text/20 bg-white p-8 text-center shadow-card">
          <h1 className="font-display text-xl font-semibold text-text-primary">
            页面加载失败
          </h1>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            {this.state.error.message || "应用遇到未知错误，请重试。"}
          </p>
          <button
            type="button"
            className="mt-6 rounded-lg bg-text-charcoal px-4 py-2 text-sm font-medium text-white transition hover:bg-text-dark"
            onClick={() => this.setState({ error: null })}
          >
            重试
          </button>
        </div>
      </div>
    );
  }
}
