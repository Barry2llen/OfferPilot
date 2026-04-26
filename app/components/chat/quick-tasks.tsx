"use client";

import Link from "next/link";
import Button from "@/app/components/ui/button";

interface QuickTasksProps {
  onPrompt: (prompt: string) => void;
  disabled: boolean;
}

const tasks = [
  {
    label: "分析简历优势",
    prompt: "请分析这份简历的主要优势和亮点。",
    icon: "📊",
  },
  {
    label: "优化项目经历",
    prompt: "根据这份简历，请帮我优化项目经历描述，使其更有影响力。",
    icon: "✨",
  },
  {
    label: "检查简历完整度",
    prompt: "请检查这份简历的完整度，指出需要补充或改进的地方。",
    icon: "🔍",
  },
];

export default function QuickTasks({ onPrompt, disabled }: QuickTasksProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {tasks.map((task) => (
        <Button
          key={task.label}
          variant="ghost"
          size="sm"
          onClick={() => onPrompt(task.prompt)}
          disabled={disabled}
        >
          <span className="mr-1">{task.icon}</span>
          {task.label}
        </Button>
      ))}
    </div>
  );
}
