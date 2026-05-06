"use client";

import { useState } from "react";
import Sidebar from "@/app/components/layout/sidebar";
import ResumeUploadStatus from "@/app/components/resumes/resume-upload-status";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="flex h-full w-full">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((collapsed) => !collapsed)}
      />
      <div
        className={`flex flex-col flex-1 min-w-0 transition-[padding] duration-200 ${
          sidebarCollapsed ? "lg:pl-16" : "lg:pl-60"
        }`}
      >
        <main className="flex-1 overflow-y-auto">{children}</main>
        <ResumeUploadStatus />
      </div>
    </div>
  );
}
