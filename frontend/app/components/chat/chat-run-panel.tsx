import FormDrawer from "@/app/components/ui/form-drawer";
import { useMediaQuery } from "@/app/hooks/use-media-query";
import type { QueryDraft } from "./query-decision-composer";
import { useState, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import type {
  ChatRun,
  PendingInput,
  ConnectionState,
  InputAnswer,
} from "@/app/lib/api/types";
import Button from "@/app/components/ui/button";
import { useToast } from "@/app/components/ui/toast";
import QueryDecisionComposer from "./query-decision-composer";
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
  const { addToast } = useToast();
  const mobile = useMediaQuery("(max-width: 767px)");
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<QueryDraft>({ selectedIds: [], freeText: "", note: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (answer: InputAnswer) => {
    if (busy) return;
    setBusy(true);
    try {
      await onAnswer(input, answer);
      setOpen(false);
    } catch (error) {
      addToast(error instanceof Error && error.message ? error.message : t("errors.submitFailed"), "error");
      setBusy(false);
    }
  };
  const form = (
    <fieldset disabled={busy} className="min-w-0">
      {input.type === "query" ? (
        <QueryDecisionComposer
          input={input}
          draft={draft}
          onDraftChange={setDraft}
          onAnswer={(answer) => {
            void submit(answer);
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
    </fieldset>);
  if (!mobile) return form;
  return <>
    <div className="rounded-xl border border-border-default bg-surface-secondary p-4">
      <p className="mb-3 text-sm font-semibold">{input.type === "query" ? input.question : input.message}</p>
      {input.type === "query" && <p className="mb-4 line-clamp-2 text-sm text-text-secondary">{input.options.map((option) => option.label).join(" · ")}</p>}
      <Button className="w-full" onClick={() => setOpen(true)}>{t("appearance.answer")}</Button>
    </div>
    <FormDrawer busy={busy} open={open} title={t("chatRuns.waitingInput")} onClose={() => setOpen(false)}>{form}</FormDrawer>
  </>;

}

export default function ChatRunPanel({
  runs,
  inputs,
  connectionState,
  onAnswer,
  onCancel,
  onCancelQueued,
  pendingInputRef,
}: {
  runs: ChatRun[];
  inputs: PendingInput[];
  connectionState: ConnectionState;
  onAnswer: (input: PendingInput, answer: InputAnswer) => Promise<void>;
  onCancel: (runId: string) => Promise<void>;
  onCancelQueued: () => Promise<void>;
  pendingInputRef?: RefObject<HTMLDivElement | null>;
}) {
  const { t } = useTranslation();
  const queued = runs.filter((run) => run.status === "queued");
  const interrupted = runs.filter(needsRunNotice);
  return (
    <div
      className="run-panel space-y-3 py-3"
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
      {inputs.map((input, index) => (
        <div
          key={input.request_id}
          ref={index === 0 ? pendingInputRef : undefined}
          tabIndex={-1}
          role="group"
          className="relative"
          aria-label={input.type === "query" ? input.question : input.message || t("chatRuns.waitingInput")}
        >
          <span data-pending-start aria-hidden="true" className="pointer-events-none absolute left-0 top-0 h-px w-px" />
          <InputCard input={input} onAnswer={onAnswer} />
        </div>
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
