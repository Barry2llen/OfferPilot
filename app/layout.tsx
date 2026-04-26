import type { Metadata } from "next";
import { AppProvider } from "@/app/lib/context/app-context";
import { ToastProvider } from "@/app/components/ui/toast";
import Sidebar from "@/app/components/layout/sidebar";
import ContextBar from "@/app/components/layout/context-bar";
import "./globals.css";

export const metadata: Metadata = {
  title: "OfferPilot - AI 求职助手",
  description: "基于大模型与 Agent 工作流的求职 AI 工具",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="h-full bg-surface-primary text-text-primary font-sans">
        <AppProvider>
          <ToastProvider>
            <div className="flex h-full">
              <Sidebar />
              <div className="flex flex-col flex-1 min-w-0 lg:ml-60">
                <ContextBar />
                <main className="flex-1 overflow-y-auto">{children}</main>
              </div>
            </div>
          </ToastProvider>
        </AppProvider>
      </body>
    </html>
  );
}
