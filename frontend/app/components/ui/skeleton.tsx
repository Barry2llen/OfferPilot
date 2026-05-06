interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div className={`animate-pulse rounded-2xl bg-border-light ${className}`} />
  );
}

export function ResumeCardSkeleton() {
  return (
    <div className="rounded-[20px] border border-border-light bg-white p-4 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-48 rounded-lg" />
          <Skeleton className="h-4 w-32 rounded-lg" />
          <Skeleton className="mt-2 h-4 w-full rounded-lg" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-8 w-14 rounded-lg" />
          <Skeleton className="h-8 w-14 rounded-lg" />
        </div>
      </div>
    </div>
  );
}
