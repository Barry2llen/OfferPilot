export default function SelectionsLoading() {
  return (
    <div className="max-w-2xl mx-auto p-6 animate-pulse">
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="h-7 w-32 bg-border-default rounded mb-2" />
          <div className="h-4 w-48 bg-border-light rounded" />
        </div>
        <div className="h-10 w-28 bg-border-default rounded-xl" />
      </div>
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 bg-border-light rounded-[20px]" />
        ))}
      </div>
    </div>
  );
}
