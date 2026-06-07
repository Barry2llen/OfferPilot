export default function ResumesLoading() {
  return (
    <div className="electron-titlebar-safe-top min-h-full bg-white">
      <div className="mx-auto max-w-[1040px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6">
        <div className="space-y-8">
          <div className="h-[232px] animate-pulse rounded-[20px] border border-dashed border-[#c3c5d8] bg-white shadow-brand-glow" />
          <section>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="mb-2 h-5 w-24 animate-pulse rounded-lg bg-border-default" />
                <div className="h-4 w-48 animate-pulse rounded-lg bg-border-light" />
              </div>
              <div className="flex gap-2">
                <div className="h-7 w-7 animate-pulse rounded-full bg-border-light" />
                <div className="h-7 w-7 animate-pulse rounded-full bg-border-light" />
              </div>
            </div>
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-[88px] animate-pulse rounded-xl bg-border-light"
                />
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
