import { NavLink, Outlet } from "react-router";
import { useTranslation } from "react-i18next";

export default function SettingsPage() {
  const { t } = useTranslation();

  return (
    <div className="electron-titlebar-safe-top min-h-full bg-white">
      <div className="mx-auto max-w-[1040px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6">
        <header>
          <h1 className="font-display text-2xl font-semibold text-text-primary">
            {t("settings.title")}
          </h1>
          <p className="mt-1 text-sm text-text-muted">
            {t("settings.description")}
          </p>
        </header>

        <nav className="mt-6" aria-label={t("settings.tabsLabel")}>
          <div className="grid w-full grid-cols-2 rounded-full border border-[#e6e1dc] bg-white p-0.5 shadow-[0_1px_8px_rgba(24,24,24,0.06)] sm:inline-grid sm:w-auto">
            <NavLink
              to="providers"
              end
              className={({ isActive }) =>
                `rounded-full px-4 py-2 text-center text-xs font-semibold transition-colors sm:min-w-[132px] ${
                  isActive
                    ? "bg-text-charcoal text-white shadow-sm"
                    : "text-text-secondary hover:bg-surface-secondary"
                }`
              }
            >
              {t("settings.modelConfigTab")}
            </NavLink>
            <NavLink
              to="advanced"
              className={({ isActive }) =>
                `rounded-full px-4 py-2 text-center text-xs font-semibold transition-colors sm:min-w-[132px] ${
                  isActive
                    ? "bg-text-charcoal text-white shadow-sm"
                    : "text-text-secondary hover:bg-surface-secondary"
                }`
              }
            >
              {t("settings.advancedTab")}
            </NavLink>
          </div>
        </nav>

        <div className="mt-6">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
