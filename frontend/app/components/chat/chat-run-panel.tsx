import { useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  ChatRun,
  PendingInput,
  ConnectionState,
  InputAnswer,
} from "@/app/lib/api/types";
import Button from "@/app/components/ui/button";
import { QueryDecisionComposer } from "./chat-input";
import { needsRunNotice } from "@/app/lib/chat/run-state";

const MAX_RUN_NOTICES = 3;

function InputCard({
  input,
  onAnswer,
}: {
  input: PendingInput;
  onAnswer: (input: PendingInput, answer: InputAnswer) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const submit = async (answer: InputAnswer) => {
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
  connectionState: ConnectionState;
  onAnswer: (input: PendingInput, answer: InputAnswer) => Promise<void>;
  onCancel: (runId: string) => Promise<void>;
  onCancelQueued: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const queued = runs.filter((run) => run.status === "queued");
  const interrupted = runs.filter(needsRunNotice);
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
      {interrupted.slice(-MAX_RUN_NOTICES).map((run) => (
        <p key={run.run_id} className="text-xs text-warning-text">
          {run.status === "failed"
            ? t("chatRuns.failed", { prompt: run.prompt })
            : run.status === "cancelled"
              ? t("chatRuns.cancelled", { prompt: run.prompt })
              : t("chatRuns.interrupted", { prompt: run.prompt })}
          {run.detail && (
            <span className="block break-words">{run.detail}</span>
          )}
        </p>
      ))}
    </div>
  );
}
