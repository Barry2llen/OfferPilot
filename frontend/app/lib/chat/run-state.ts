import type { ChatRun, ChatRunStatus, PendingInput } from "@/app/lib/api/types";
import type { ChatStreamEvent } from "./types";

export function isTerminal(status: ChatRunStatus): boolean {
  return ["completed", "failed", "cancelled", "interrupted"].includes(status);
}

export function mergeRuns(current: ChatRun[], incoming: ChatRun[]): ChatRun[] {
  const rows = new Map(current.map((run) => [run.run_id, run]));
  for (const run of incoming) {
    const old = rows.get(run.run_id);
    if (
      old &&
      ((isTerminal(old.status) && !isTerminal(run.status)) ||
        (old.last_event_id > run.last_event_id && !isTerminal(run.status)))
    )
      continue;
    rows.set(run.run_id, run);
  }
  return [...rows.values()].sort((a, b) => a.sequence - b.sequence);
}

export function eventSequence(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

export function isProjectedEvent(
  value: unknown,
  runId: string,
  threadId: string,
): value is ChatStreamEvent {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  if (
    typeof item.event !== "string" ||
    !item.data ||
    typeof item.data !== "object"
  )
    return false;
  const data = item.data as Record<string, unknown>;
  if (
    data.run_id !== runId ||
    data.thread_id !== threadId ||
    eventSequence(data.event_id) === null
  )
    return false;
  return (
    !["tool_start", "tool_end", "tool_error"].includes(item.event) ||
    (typeof data.tool_call_id === "string" && data.tool_call_id.length > 0)
  );
}

export function pendingInput(
  value: unknown,
  runId: string,
  threadId: string,
): PendingInput | null {
  if (!value || typeof value !== "object") return null;
  const input = value as Record<string, unknown>;
  if (
    typeof input.request_id !== "string" ||
    !input.request_id ||
    input.run_id !== runId ||
    input.thread_id !== threadId ||
    (input.tool_call_id !== null && typeof input.tool_call_id !== "string") ||
    (input.type !== "query" && input.type !== "error")
  )
    return null;
  for (const key of [
    "message",
    "question",
    "firstChoice",
    "secondChoice",
    "thirdChoice",
    "firstChoiceDescription",
    "secondChoiceDescription",
    "thirdChoiceDescription",
  ]) {
    if (input[key] != null && typeof input[key] !== "string") return null;
  }
  return input as unknown as PendingInput;
}

export function createIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === "function")
    return globalThis.crypto.randomUUID();
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

export function isRunStatus(value: unknown): value is ChatRunStatus {
  return (
    typeof value === "string" &&
    [
      "queued",
      "running",
      "waiting_input",
      "completed",
      "failed",
      "cancelled",
      "interrupted",
    ].includes(value)
  );
}

export function needsRunNotice(run: ChatRun): boolean {
  return (
    isTerminal(run.status) &&
    run.status !== "completed" &&
    (run.status !== "cancelled" || Boolean(run.detail))
  );
}
