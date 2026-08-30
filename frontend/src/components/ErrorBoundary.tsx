import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Without this, any throw during render or in an effect unmounts the whole tree and leaves a
 * blank page - no message, nothing in the server logs, and no way for the user to tell the
 * difference between "broken" and "still loading". Showing the message and a reload button
 * keeps a crash diagnosable from the device it happened on. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
        <p className="text-base font-semibold text-gray-900 dark:text-white">
          Xatolik yuz berdi
        </p>
        <pre className="max-h-40 max-w-full overflow-auto whitespace-pre-wrap rounded-lg bg-gray-100 p-3 text-left text-xs text-gray-600 dark:bg-white/5 dark:text-gray-400">
          {error.message}
        </pre>
        <button
          onClick={() => window.location.reload()}
          className="rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-white"
        >
          Qayta yuklash
        </button>
      </div>
    );
  }
}
