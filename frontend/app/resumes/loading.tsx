export default function ResumesLoading() {
  return (
    <div className="max-w-2xl mx-auto p-6 animate-pulse">
      <div className="mb-6">
        <div className="h-7 w-24 bg-border-default rounded mb-2" />
        <div className="h-4 w-48 bg-border-light rounded" />
      </div>
      <div className="h-48 bg-border-light rounded-[20px] mb-6" />
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-28 bg-border-light rounded-[20px]" />
        ))}
      </div>
    </div>
  );
}
