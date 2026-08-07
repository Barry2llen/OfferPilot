export interface ContextWindowModel {
  context_window_tokens: number;
}

export function shouldWarnForSmallerContextWindow(
  hasExistingThread: boolean,
  currentModel: ContextWindowModel | null,
  nextModel: ContextWindowModel | null,
): boolean {
  return Boolean(
    hasExistingThread &&
      currentModel &&
      nextModel &&
      nextModel.context_window_tokens < currentModel.context_window_tokens,
  );
}
