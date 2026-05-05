import type { Metadata } from "next";
import { AppProvider } from "@/app/lib/context/app-context";
import { ResumeUploadProvider } from "@/app/lib/context/resume-upload-context";
import { ToastProvider } from "@/app/components/ui/toast";
import AppShell from "@/app/components/layout/app-shell";
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
            <ResumeUploadProvider>
              <AppShell>{children}</AppShell>
            </ResumeUploadProvider>
          </ToastProvider>
        </AppProvider>
      </body>
    </html>
  );
}
