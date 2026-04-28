"use client";

import Button from "@/app/components/ui/button";

export default function RootError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center max-w-md px-4">
        <div className="w-14 h-14 rounded-full bg-error-bg flex items-center justify-center mx-auto mb-4">
          <svg
            className="w-7 h-7 text-error-text"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
            />
          </svg>
        </div>
        <h1 className="font-display text-xl font-semibold text-text-primary mb-2">
          出现错误
        </h1>
        <p className="text-sm text-text-secondary mb-6">
          {error.message || "发生了意外错误，请重试"}
        </p>
        <Button onClick={unstable_retry}>重试</Button>
      </div>
    </div>
  );
}
