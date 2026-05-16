"use client";
import React from "react";

interface Props {
  children: React.ReactNode;
  label: string;            // shown in fallback, e.g. "Map", "Incident list"
  className?: string;
}

interface State {
  error: Error | null;
}

/**
 * Catches render + synchronous errors from child components. useEffect errors
 * that throw synchronously are also caught. Keeps the rest of the dashboard
 * functional when one panel blows up.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`ErrorBoundary[${this.props.label}]:`, error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div className={`flex h-full items-center justify-center bg-bg-panel text-fg-muted ${this.props.className ?? ""}`}>
          <div className="max-w-md text-center px-6">
            <div className="text-fg-secondary">{this.props.label} unavailable</div>
            <div className="mono text-xs mt-2 text-status-warn break-words">
              {this.state.error.message}
            </div>
            <button
              onClick={this.reset}
              className="mono mt-3 border border-border-strong px-2 py-1 text-xs text-fg-primary hover:bg-bg-elev"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
