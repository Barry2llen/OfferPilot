import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ChatRun, PendingInput } from "@/app/lib/api/types";
import Button from "@/app/components/ui/button";
import { QueryDecisionComposer } from "./chat-input";

function InputCard({
  input,
  onAnswer,
}: {
  input: PendingInput;
  onAnswer: (
    input: PendingInput,
    answer: Record<string, unknown>,
  ) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const submit = async (answer: Record<string, unknown>) => {
    if (busy) return;
    setBusy(true);
    try {
      await onAnswer(input, answer);
    } catch {
      setBusy(false);
    }
  };
  return (
    <fieldset disabled={busy} className="min-w-0">
      {input.type === "query" ? (
        <QueryDecisionComposer
          input={input}
          onAnswer={(choice, note) => {
            void submit({ choice, note });
          }}
        />
      ) : (
        <div className="rounded-xl bg-warning-bg p-3 text-sm">
          <p>{input.message}</p>
          <Button
            size="sm"
            onClick={() => {
              void submit({ type: "retry" });
            }}
          >
            {t("chat.retry")}
          </Button>
        </div>
      )}
    </fieldset>
  );
}

export default function ChatRunPanel({
  runs,
  inputs,
  connectionState,
  onAnswer,
  onCancel,
  onCancelQueued,
}: {
  runs: ChatRun[];
  inputs: PendingInput[];
  connectionState: string;
  onAnswer: (
    input: PendingInput,
    answer: Record<string, unknown>,
  ) => Promise<void>;
  onCancel: (runId: string) => Promise<void>;
  onCancelQueued: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const queued = runs.filter((run) => run.status === "queued");
  const interrupted = runs.filter((run) =>
    ["interrupted", "failed", "cancelled"].includes(run.status),
  );
  return (
    <div
      className="max-h-[45vh] overflow-y-auto space-y-3 px-4 sm:px-6"
      aria-live="polite"
    >
      {connectionState === "reconnecting" && (
        <p className="text-sm text-warning-text">
          {t("chatRuns.reconnecting")}
        </p>
      )}
      {queued.length > 0 && (
        <div className="rounded-xl border border-border-light p-3 text-sm">
          <div className="flex items-center justify-between">
            <span>{t("chatRuns.queued", { count: queued.length })}</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                void onCancelQueued();
              }}
            >
              {t("chatRuns.cancelQueued")}
            </Button>
          </div>
          {queued.map((run) => (
            <div
              key={run.run_id}
              className="flex items-center justify-between gap-2 py-1"
            >
              <span className="truncate">
                {run.prompt || t("chatRuns.attachments")}
              </span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  void onCancel(run.run_id);
                }}
              >
                {t("chatRuns.remove")}
              </Button>
            </div>
          ))}
          <p className="text-xs text-text-muted">{t("chatRuns.stopNotice")}</p>
        </div>
      )}
      {inputs.map((input) => (
        <InputCard key={input.request_id} input={input} onAnswer={onAnswer} />
      ))}
      {interrupted.slice(-3).map((run) => (
        <p key={run.run_id} className="text-xs text-warning-text">
          {t(`chatRuns.${run.status}`)} {run.prompt}
          {run.detail && <span className="block break-words">{run.detail}</span>}
        </p>
      ))}
    </div>
  );
}
