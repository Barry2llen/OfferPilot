import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import QuickTasks from "@/app/components/chat/quick-tasks";
import { buttonClassName } from "@/app/components/ui/button";

interface ChatWelcomeProps {
  hasNoModel: boolean;
  onPrompt: (prompt: string) => void;
}


export default function ChatWelcome({ hasNoModel, onPrompt }: ChatWelcomeProps) {
  const { t } = useTranslation();

  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="w-full max-w-lg">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-blue/10">
          <svg
            className="h-8 w-8 text-brand-blue"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M13 10V3L4 14h7v7l9-11h-7z"
            />
          </svg>
        </div>

        <h1 className="font-display text-2xl font-semibold text-text-primary">
          {t("welcome.greeting")}
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          {t("welcome.description")}
        </p>

        {hasNoModel ? (
          <div className="mt-6 rounded-2xl border border-dashed border-border-default p-6 text-center">
            <p className="mb-4 text-sm text-text-secondary">
              {t("welcome.configureFirst")}
            </p>
            <Link to="/settings/providers" className={buttonClassName()}>
              {t("welcome.goToSettings")}
            </Link>
          </div>
        ) : (
          <>
            <div className="mt-8 flex justify-center w-full">
              <QuickTasks onPrompt={onPrompt} disabled={false} />
            </div>

            <p className="mt-6 text-center text-[11px] text-text-muted">
              {t("welcome.comingSoon")}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
