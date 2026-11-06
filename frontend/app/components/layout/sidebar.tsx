import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";
import { MessageSquare, FileUser, BriefcaseBusiness, Folder, Settings, Monitor } from "lucide-react";
import { getCurrentLocale, setLocale, type Locale } from "@/app/lib/i18n";
import { useTheme, type ThemeMode } from "@/app/lib/theme";

const items = [
  { to: "/", label: "nav.aiChat", short: "chat", icon: MessageSquare },
  { to: "/resumes", label: "nav.resumes", short: "resumes", icon: FileUser },
  { to: "/job-descriptions", label: "nav.jd", short: "jd", icon: BriefcaseBusiness },
  { to: "/files", label: "nav.files", short: "files", icon: Folder },
  { to: "/settings", label: "nav.settings", short: "settings", icon: Settings },
];
export default function Sidebar({ historyRef }: { historyRef: (node: HTMLDivElement | null) => void }) {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  return <aside className="app-sidebar">
    <div className="sidebar-brand app-region-drag"><span className="brand-full">OfferPilot</span><span className="brand-short">OP</span></div>
    <nav className="primary-nav" aria-label={t("nav.toggle")}>
      {items.map(({ to, label, short, icon: Icon }) => <NavLink key={to} to={to} end={to === "/"} title={t(label)} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
        <Icon size={20} strokeWidth={1.7} /><span className="nav-full">{t(label)}</span><span className="nav-short">{t(`mobileNav.${short}`)}</span>
      </NavLink>)}
    </nav>
    <div className="sidebar-history" ref={historyRef} />
    <footer className="sidebar-footer">
      <label><select aria-label={t("language.switchTo")} value={getCurrentLocale()} onChange={(e) => void setLocale(e.target.value as Locale)}><option value="zh-CN">{t("language.chinese")}</option><option value="en-US">{t("language.english")}</option></select></label>
      <label><Monitor size={16} /><select aria-label={t("appearance.theme")} value={theme} onChange={(e) => setTheme(e.target.value as ThemeMode)}>{(["light", "dark", "system"] as const).map((mode) => <option key={mode} value={mode}>{t(`appearance.${mode}`)}</option>)}</select></label>
      <p>{t("nav.version")}</p>
    </footer>
  </aside>;
}
