import { Component, type ErrorInfo, type ReactNode } from "react";
import i18n from "@/app/lib/i18n";

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
            {i18n.t("app.errorTitle")}
          </h1>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            {this.state.error.message || i18n.t("app.errorDescription")}
          </p>
          <button
            type="button"
            className="mt-6 rounded-lg bg-text-charcoal px-4 py-2 text-sm font-medium text-white transition hover:bg-text-dark"
            onClick={() => window.location.reload()}
          >
            {i18n.t("app.reload")}
          </button>
        </div>
      </div>
    );
  }
}
