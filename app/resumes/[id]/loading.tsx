export default function ResumeDetailLoading() {
  return (
    <div className="max-w-3xl mx-auto p-6 animate-pulse">
      <div className="h-8 w-16 bg-border-default rounded-lg mb-6" />
      <div className="mb-6">
        <div className="h-7 w-48 bg-border-default rounded mb-2" />
        <div className="h-5 w-32 bg-border-light rounded" />
      </div>
      <div className="h-[400px] bg-border-light rounded-[20px] mb-6" />
      <div className="h-64 bg-border-light rounded-[20px]" />
    </div>
  );
}
