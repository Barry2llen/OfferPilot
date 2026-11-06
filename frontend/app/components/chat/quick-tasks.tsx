import { FileSearch, PenLine, ListChecks } from "lucide-react";
interface QuickTasksProps {
  onPrompt: (prompt: string) => void;
  disabled: boolean;
}

const tasks = [
  {
    labelKey: "quickTasks.analyze",
    descriptionKey: "quickTasks.analyzeDescription",
    promptKey: "quickTasks.analyzePrompt",
    icon: FileSearch,
  },
  {
    labelKey: "quickTasks.improve",
    descriptionKey: "quickTasks.improveDescription",
    promptKey: "quickTasks.improvePrompt",
    icon: PenLine,
  },
  {
    labelKey: "quickTasks.check",
    descriptionKey: "quickTasks.checkDescription",
    promptKey: "quickTasks.checkPrompt",
    icon: ListChecks,
  },
];

export default function QuickTasks({ onPrompt, disabled }: QuickTasksProps) {
  const { t } = useTranslation();

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full">
      {tasks.map((task) => (
        <button
          key={task.labelKey}
          onClick={() => onPrompt(t(task.promptKey))}
          disabled={disabled}
          className="text-left rounded-xl bg-surface-primary p-4 transition-all hover:bg-black/[0.04] active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none group border border-border-default hover:border-border-default/50 hover:shadow-sm"
        >
          <div className="text-text-secondary leading-none mb-3">
            <task.icon size={20} strokeWidth={1.7} />
          </div>
          <h2 className="text-sm font-semibold text-text-primary group-hover:text-primary-700 transition-colors">
            {t(task.labelKey)}
          </h2>
          <p className="mt-1 text-xs text-text-muted leading-relaxed">
            {t(task.descriptionKey)}
          </p>
        </button>
      ))}
    </div>
  );
}
import { useTranslation } from "react-i18next";
