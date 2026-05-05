"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  {
    href: "/",
    label: "AI 对话",
    icon: ChatIcon,
    active: true,
  },
  {
    href: "/resumes",
    label: "简历库",
    icon: DocIcon,
    active: true,
  },
  {
    href: "/settings/providers",
    label: "模型配置",
    icon: SettingsIcon,
    active: true,
  },
];

const futureItems = [
  { label: "JD 分析" },
  { label: "简历优化" },
  { label: "模拟面试" },
  { label: "求职跟踪" },
  { label: "知识库" },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  return (
    <>
      <button
        onClick={onToggle}
        className="fixed top-4 left-4 z-50 lg:hidden p-2 rounded-lg bg-white shadow-card border border-border-default"
        aria-label="Toggle sidebar"
        aria-expanded={!collapsed}
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <aside
        className={`fixed top-0 left-0 z-40 h-full bg-white border-r border-border-light flex flex-col transition-all duration-200 ${
          collapsed ? "-translate-x-full lg:translate-x-0 lg:w-16" : "w-60"
        }`}
      >
        <div className="h-14 flex items-center px-4 border-b border-border-light">
          <span className="font-display text-lg font-semibold text-text-primary tracking-tight truncate">
            {collapsed ? "OP" : "OfferPilot"}
          </span>
        </div>

        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-1">
          {navItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.active ? item.href : "#"}
                className={`flex items-center gap-3 px-3 py-2 rounded-full text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-black/5 text-text-dark"
                    : "text-text-muted hover:text-text-dark hover:bg-black/[0.03]"
                } ${!item.active ? "opacity-40 pointer-events-none" : ""}`}
                title={item.label}
              >
                <item.icon className="w-4 h-4 shrink-0" />
                {!collapsed && <span>{item.label}</span>}
                {!item.active && !collapsed && (
                  <span className="ml-auto text-[10px] text-text-muted bg-border-light px-1.5 py-0.5 rounded-full">
                    规划中
                  </span>
                )}
              </Link>
            );
          })}

          <div className="pt-4 pb-1">
            <div className="px-3">
              {!collapsed && (
                <p className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-2">
                  后续功能
                </p>
              )}
            </div>
            {futureItems.map((item) => (
              <div
                key={item.label}
                className="flex items-center gap-3 px-3 py-1.5 text-sm text-text-muted/50 opacity-40 pointer-events-none"
                title={collapsed ? item.label : undefined}
              >
                <span className="w-4 h-4 shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </div>
            ))}
          </div>
        </nav>

        <div className="p-3 border-t border-border-light">
          {!collapsed && (
            <p className="text-[10px] text-text-muted text-center">
              OfferPilot v0.1
            </p>
          )}
          <button
            onClick={onToggle}
            className="hidden lg:block w-full mt-1 p-1 rounded-lg hover:bg-black/[0.03] transition-colors"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
          >
            <svg
              className={`w-4 h-4 mx-auto text-text-muted transition-transform ${
                collapsed ? "rotate-180" : ""
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        </div>
      </aside>
    </>
  );
}

function ChatIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
    </svg>
  );
}

function DocIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function SettingsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}
