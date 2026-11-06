import { NavLink, Outlet } from "react-router";
import { useTranslation } from "react-i18next";

export default function SettingsPage() {
  const { t } = useTranslation();

  return (
    <div className="electron-titlebar-safe-top min-h-full bg-surface-primary">
      <div className="mx-auto max-w-[1280px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6">
        <header>
          <h1 className="font-display text-2xl font-semibold text-text-primary">
            {t("settings.title")}
          </h1>
          <p className="mt-1 text-sm text-text-muted">
            {t("settings.description")}
          </p>
        </header>

        <nav className="mt-6" aria-label={t("settings.tabsLabel")}>
          <div className="settings-tabs">
            <NavLink to="appearance">{t("appearance.tab")}</NavLink>
            <NavLink to="providers">{t("settings.modelConfigTab")}</NavLink>
            <NavLink to="advanced">{t("settings.advancedTab")}</NavLink>
          </div>
        </nav>

        <div className="mt-6">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
