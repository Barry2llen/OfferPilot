interface QuickTasksProps {
  onPrompt: (prompt: string) => void;
  disabled: boolean;
}

const tasks = [
  {
    label: "分析简历",
    description: "帮你找到核心竞争力",
    prompt: "请分析这份简历的主要优势和亮点。",
    icon: "📊",
  },
  {
    label: "优化表述",
    description: "让项目经历更有说服力",
    prompt: "根据这份简历，请帮我优化项目经历描述，使其更有影响力。",
    icon: "✨",
  },
  {
    label: "查漏补缺",
    description: "全面检查简历完整度",
    prompt: "请检查这份简历的完整度，指出需要补充或改进的地方。",
    icon: "🔍",
  },
];

export default function QuickTasks({ onPrompt, disabled }: QuickTasksProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full">
      {tasks.map((task) => (
        <button
          key={task.label}
          onClick={() => onPrompt(task.prompt)}
          disabled={disabled}
          className="text-left rounded-2xl bg-surface-secondary p-4 transition-all hover:bg-black/[0.04] active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none group border border-transparent hover:border-border-default/50 hover:shadow-sm"
        >
          <div className="text-xl leading-none mb-3 group-hover:scale-110 transition-transform origin-bottom-left">
            {task.icon}
          </div>
          <h2 className="text-sm font-semibold text-text-primary group-hover:text-primary-700 transition-colors">
            {task.label}
          </h2>
          <p className="mt-1 text-xs text-text-muted leading-relaxed">
            {task.description}
          </p>
        </button>
      ))}
    </div>
  );
}
