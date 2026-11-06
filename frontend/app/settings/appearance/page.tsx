import { Sun, Moon, Monitor } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/app/lib/theme";
import { getCurrentLocale, setLocale, type Locale } from "@/app/lib/i18n";
import Select from "@/app/components/ui/select";
export default function AppearancePage() {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  return <div className="space-y-8">
    <section><h2 className="text-base font-semibold">{t("appearance.theme")}</h2><p className="mt-1 text-sm text-text-muted">{t("appearance.description")}</p>
      <div className="theme-options" role="group" aria-label={t("appearance.theme")}>
        {([{ mode: "light", Icon: Sun }, { mode: "dark", Icon: Moon }, { mode: "system", Icon: Monitor }] as const).map(({ mode, Icon }) => <button key={mode} aria-pressed={theme === mode} className="theme-option" onClick={() => setTheme(mode)}><Icon size={24} /><span>{t(`appearance.${mode}`)}</span></button>)}
      </div>
    </section>
    <section className="settings-row"><div><h2 className="font-semibold">{t("language.label")}</h2><p className="mt-1 text-sm text-text-muted">{t("appearance.languageHint")}</p></div><Select<Locale> aria-label={t("language.switchTo")} className="min-w-40" align="end" value={getCurrentLocale()} onChange={(value) => void setLocale(value)} options={[{ value: "zh-CN", label: t("language.chinese") }, { value: "en-US", label: t("language.english") }]} /></section>
  </div>;
}
