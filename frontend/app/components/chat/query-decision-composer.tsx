import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@/app/components/ui/button";
import type { PendingQueryInput, QueryAnswer } from "@/app/lib/api/types";

interface Props {
  input: PendingQueryInput;
  onAnswer: (answer: QueryAnswer) => void;
}

export default function QueryDecisionComposer(props: Props) {
  return <DecisionForm key={props.input.request_id} {...props} />;
}

function DecisionForm({ input, onAnswer }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [freeText, setFreeText] = useState("");
  const [note, setNote] = useState("");
  const multiple = input.selection_mode === "multiple";
  const canSubmit = selectedIds.length > 0 || Boolean(freeText.trim());

  const choose = (optionId: string) => {
    if (!multiple) {
      setSelectedIds([optionId]);
      setFreeText("");
      return;
    }
    setSelectedIds((current) => current.includes(optionId)
      ? current.filter((value) => value !== optionId)
      : [...current, optionId]);
  };
  const submit = () => {
    if (!canSubmit) return;
    onAnswer({
      selected_option_ids: input.options
        .filter((option) => selectedIds.includes(option.id))
        .map((option) => option.id),
      free_text: freeText.trim() || null,
      note: note.trim() || null,
    });
  };
  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="rounded-[1.45rem] border border-border-light bg-white px-4 py-3.5 text-text-primary shadow-[0_0_22px_rgba(44,30,116,0.16)] sm:px-5">
      <fieldset aria-describedby={`${id}-mode`}>
        <legend className="text-sm font-semibold leading-snug sm:text-base">
          {input.question}
        </legend>
        <p id={`${id}-mode`} className="mb-3 mt-1 text-xs text-text-muted">
          {t(multiple ? "chat.queryMultipleHint" : "chat.querySingleHint")}
        </p>
        <div className="space-y-1.5">
          {input.options.map((option, index) => {
            const selected = selectedIds.includes(option.id);
            return (
              <label key={option.id} className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-2xl border px-3 py-2 transition ${selected
                ? "border-primary-500/45 bg-primary-200/45"
                : "border-transparent bg-surface-secondary/70 hover:border-border-light"}`}>
                <input
                  type={multiple ? "checkbox" : "radio"}
                  name={`${id}-choice`}
                  checked={selected}
                  onChange={() => choose(option.id)}
                  aria-describedby={`${id}-option-${index}`}
                  className="mt-1 h-4 w-4 shrink-0 accent-primary-500"
                />
                <span className="min-w-0 flex-1">
                  <span className="block break-words text-sm font-semibold">
                    {option.label}
                    {index === 0 && <span className="ml-1 text-xs font-normal text-text-muted">({t("common.recommended")})</span>}
                  </span>
                  <span id={`${id}-option-${index}`} className="mt-0.5 block break-words text-xs text-text-secondary">
                    {option.description}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>
      <div className="mt-3 space-y-2.5">
        <label className="block text-xs text-text-secondary">
          {t("chat.queryFreeText")}
          <textarea
            value={freeText}
            onChange={(event) => {
              setFreeText(event.target.value);
              if (!multiple) setSelectedIds([]);
            }}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder={t("chat.queryFreeTextPlaceholder")}
            className="mt-1 block min-h-10 w-full resize-y rounded-xl border border-border-light bg-surface-secondary/50 px-3 py-2 text-sm text-text-primary outline-none focus-visible:ring-2 focus-visible:ring-primary-500/25"
          />
        </label>
        <label className="block text-xs text-text-secondary">
          {t("chat.queryNote")}
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder={t("chat.queryNoteOnlyPlaceholder")}
            className="mt-1 block min-h-10 w-full resize-y rounded-xl border border-border-light bg-surface-secondary/50 px-3 py-2 text-sm text-text-primary outline-none focus-visible:ring-2 focus-visible:ring-primary-500/25"
          />
        </label>
        <div className="flex justify-end">
          <Button type="button" onClick={submit} disabled={!canSubmit}>
            {t("chat.submit")}
          </Button>
        </div>
      </div>
    </div>
  );
}
