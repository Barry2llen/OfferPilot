"use client";

import Button from "@/app/components/ui/button";

export default function ResumesError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <div className="electron-titlebar-safe-top min-h-full bg-white">
      <div className="mx-auto max-w-[1040px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6">
      <div className="rounded-xl border border-border-light bg-white px-6 py-16 text-center shadow-card">
        <h1 className="mb-2 font-display text-xl font-semibold text-text-primary">
          简历库加载失败
        </h1>
        <p className="mb-6 text-sm text-text-secondary">{error.message}</p>
        <Button size="sm" onClick={unstable_retry}>重试</Button>
      </div>
      </div>
    </div>
  );
}
