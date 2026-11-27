/** Shared trigger styling so custom pickers match the `Select` component. */
export type SelectTriggerSize = "sm" | "md";
export type SelectTriggerVariant = "outline" | "ghost";

const triggerSizes: Record<SelectTriggerSize, string> = {
  sm: "h-8 gap-1.5 rounded-lg px-2.5 text-[13px]",
  md: "h-10 gap-2 rounded-lg px-3 text-sm",
};

const triggerVariants: Record<SelectTriggerVariant, string> = {
  outline:
    "border border-border-default bg-surface-primary text-text-primary hover:bg-surface-secondary data-[open=true]:bg-surface-secondary",
  ghost:
    "text-text-secondary hover:bg-text-primary/[0.06] hover:text-text-primary data-[open=true]:bg-text-primary/[0.06] data-[open=true]:text-text-primary",
};

export function selectTriggerClassName(size: SelectTriggerSize = "md", variant: SelectTriggerVariant = "outline"): string {
  return `inline-flex min-w-0 items-center text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${triggerSizes[size]} ${triggerVariants[variant]}`;
}

export const selectMenuClassName =
  "select-menu absolute z-50 rounded-xl border border-border-light bg-surface-primary shadow-elevated";
