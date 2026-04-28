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
    <div className="max-w-2xl mx-auto p-6">
      <div className="text-center py-20">
        <h1 className="font-display text-xl font-semibold text-text-primary mb-2">
          加载失败
        </h1>
        <p className="text-sm text-text-secondary mb-6">{error.message}</p>
        <Button onClick={unstable_retry}>重试</Button>
      </div>
    </div>
  );
}
