import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";
import { MessageSquare, FileUser, BriefcaseBusiness, Folder, Settings, Monitor, Sun, Moon, Languages } from "lucide-react";
import Select from "@/app/components/ui/select";
import { getCurrentLocale, setLocale, type Locale } from "@/app/lib/i18n";
import { useTheme, type ThemeMode } from "@/app/lib/theme";
import SidebarResizer from "./sidebar-resizer";

const items = [
  { to: "/", label: "nav.aiChat", short: "chat", icon: MessageSquare },
  { to: "/resumes", label: "nav.resumes", short: "resumes", icon: FileUser },
  { to: "/job-descriptions", label: "nav.jd", short: "jd", icon: BriefcaseBusiness },
  { to: "/files", label: "nav.files", short: "files", icon: Folder },
  { to: "/settings", label: "nav.settings", short: "settings", icon: Settings },
];
export default function Sidebar({ historyRef, width, onWidthChange, onWidthCommit }: {
  historyRef: (node: HTMLDivElement | null) => void;
  width: number;
  onWidthChange: (width: number) => void;
  onWidthCommit: (width: number) => void;
}) {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  return <aside className="app-sidebar">
    <div className="sidebar-brand app-region-drag">
      <span className="brand-full">OfferPilot</span>
      <span className="brand-version">{t("nav.version")}</span>
      <span className="brand-short">OP</span>
    </div>
    <nav className="primary-nav" aria-label={t("nav.toggle")}>
      {items.map(({ to, label, short, icon: Icon }) => <NavLink key={to} to={to} end={to === "/"} title={t(label)} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
        <Icon size={20} strokeWidth={1.7} /><span className="nav-full">{t(label)}</span><span className="nav-short">{t(`mobileNav.${short}`)}</span>
      </NavLink>)}
    </nav>
    <div className="sidebar-history" ref={historyRef} />
    <footer className="sidebar-footer">
      <Select<Locale> aria-label={t("language.switchTo")} variant="ghost" size="sm" placement="top" className="min-w-0" triggerClassName="px-2"
        icon={<Languages size={15} aria-hidden="true" />} value={getCurrentLocale()} onChange={(value) => void setLocale(value)}
        options={[{ value: "zh-CN", label: t("language.chinese") }, { value: "en-US", label: t("language.english") }]} />
      <Select<ThemeMode> aria-label={t("appearance.theme")} variant="ghost" size="sm" placement="top" align="end" className="min-w-0" triggerClassName="px-2"
        icon={<ThemeIcon size={15} aria-hidden="true" />} value={theme} onChange={setTheme}
        options={(["light", "dark", "system"] as const).map((mode) => ({ value: mode, label: t(`appearance.${mode}`) }))} />
    </footer>
    <SidebarResizer width={width} onChange={onWidthChange} onCommit={onWidthCommit} />
  </aside>;
}
