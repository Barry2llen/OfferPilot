"use client";

import Link from "next/link";
import Button, { buttonClassName } from "@/app/components/ui/button";

export default function ResumeDetailError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <div className="max-w-3xl mx-auto p-6">
      <div className="text-center py-20">
        <h1 className="font-display text-xl font-semibold text-text-primary mb-2">
          加载失败
        </h1>
        <p className="text-sm text-text-secondary mb-6">{error.message}</p>
        <div className="flex gap-3 justify-center">
          <Button onClick={unstable_retry}>重试</Button>
          <Link
            href="/resumes"
            className={buttonClassName({ variant: "ghost" })}
          >
            返回列表
          </Link>
        </div>
      </div>
    </div>
  );
}
