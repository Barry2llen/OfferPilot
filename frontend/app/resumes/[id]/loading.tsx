export default function ResumeDetailLoading() {
  return (
    <div className="electron-titlebar-safe-top min-h-full bg-white">
      <div className="mx-auto max-w-[1080px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6">
        <div className="mb-4 h-9 w-32 animate-pulse rounded-full bg-border-light" />
        <div className="flex min-h-[680px] animate-pulse flex-col bg-white lg:min-h-[calc(100vh-7.5rem)]">
          <div className="flex flex-col gap-4 border-b border-border-light py-5 sm:py-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="mb-3 h-8 w-56 rounded-lg bg-border-default" />
              <div className="h-5 w-64 rounded-lg bg-border-light" />
            </div>
            <div className="flex gap-3">
              <div className="h-7 w-16 rounded-full bg-border-light" />
              <div className="h-9 w-44 rounded-full bg-border-light" />
            </div>
          </div>
          <div className="mx-auto w-full max-w-[920px] space-y-8 py-7">
            <div className="h-28 rounded-xl bg-border-light" />
            <div className="h-16 rounded-xl bg-border-light" />
            <div className="h-48 rounded-xl bg-border-light" />
          </div>
          <div className="mt-auto flex flex-col gap-3 border-t border-border-light py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="h-8 w-20 rounded-full bg-border-light" />
            <div className="flex gap-3">
              <div className="h-8 w-20 rounded-full bg-border-light" />
              <div className="h-8 w-32 rounded-full bg-border-light" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
