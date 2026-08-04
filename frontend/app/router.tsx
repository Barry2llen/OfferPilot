import { lazy, Suspense } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import AppErrorBoundary from "@/app/components/layout/app-error-boundary";
import AppShell from "@/app/components/layout/app-shell";
import { ToastProvider } from "@/app/components/ui/toast";
import { AppProvider } from "@/app/lib/context/app-context";
import { ResumeUploadProvider } from "@/app/lib/context/resume-upload-context";

const HomePage = lazy(() => import("@/app/page"));
const FilesPage = lazy(() => import("@/app/files/page"));
const JobDescriptionsPage = lazy(() => import("@/app/job-descriptions/page"));
const JobDescriptionDetailPage = lazy(
  () => import("@/app/job-descriptions/[id]/page")
);
const ResumesPage = lazy(() => import("@/app/resumes/page"));
const ResumeDetailPage = lazy(() => import("@/app/resumes/[id]/page"));
const SettingsPage = lazy(() => import("@/app/settings/page"));
const ProvidersPage = lazy(() => import("@/app/settings/providers/page"));
const SelectionsPage = lazy(() => import("@/app/settings/selections/page"));

export default function AppRouter() {
  return (
    <BrowserRouter>
      <AppProvider>
        <ToastProvider>
          <ResumeUploadProvider>
            <AppErrorBoundary>
              <AppShell>
                <Suspense fallback={<RouteLoading />}>
                  <Routes>
                    <Route path="/" element={<HomePage />} />
                    <Route path="/files" element={<FilesPage />} />
                    <Route
                      path="/job-descriptions"
                      element={<JobDescriptionsPage />}
                    />
                    <Route
                      path="/job-descriptions/:id"
                      element={<JobDescriptionDetailPage />}
                    />
                    <Route path="/resumes" element={<ResumesPage />} />
                    <Route
                      path="/resumes/:id"
                      element={<ResumeDetailPage />}
                    />
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route
                      path="/settings/providers"
                      element={<ProvidersPage />}
                    />
                    <Route
                      path="/settings/selections"
                      element={<SelectionsPage />}
                    />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </Suspense>
              </AppShell>
            </AppErrorBoundary>
          </ResumeUploadProvider>
        </ToastProvider>
      </AppProvider>
    </BrowserRouter>
  );
}

function RouteLoading() {
  return (
    <div className="flex min-h-full items-center justify-center bg-white p-8">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-border-default border-t-primary-600" />
    </div>
  );
}
