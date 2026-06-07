import type { Metadata } from "next";
import { DM_Sans, Outfit, Roboto } from "next/font/google";
import { AppProvider } from "@/app/lib/context/app-context";
import { ResumeUploadProvider } from "@/app/lib/context/resume-upload-context";
import { ToastProvider } from "@/app/components/ui/toast";
import AppShell from "@/app/components/layout/app-shell";
import "./globals.css";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
});

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
});

const roboto = Roboto({
  subsets: ["latin"],
  variable: "--font-roboto",
  weight: ["400", "500", "700"],
});

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
    <html
      lang="zh-CN"
      className={`${dmSans.variable} ${outfit.variable} ${roboto.variable} h-full antialiased`}
    >
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
