import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const apiPaths = [
  "/ai",
  "/job-descriptions",
  "/model-providers",
  "/model-selections",
  "/resumes",
  "/health",
];

function isSpaNavigationRequest(
  method: string | undefined,
  url: string | undefined,
  accept: string | undefined,
  contentType: string | undefined,
  fetchDestination: string | undefined,
  fetchMode: string | undefined,
): boolean {
  if (!url) {
    return false;
  }

  if (method !== "GET" && method !== "HEAD") {
    return false;
  }

  if (contentType && !contentType.toLowerCase().startsWith("text/html")) {
    return false;
  }

  const isDocumentNavigation = fetchDestination
    ? fetchDestination === "document" && fetchMode === "navigate"
    : accept?.includes("text/html") === true;
  if (!isDocumentNavigation) {
    return false;
  }

  const pathname =
    new URL(url, "http://127.0.0.1").pathname.replace(/\/+$/, "") || "/";

  return (
    pathname === "/resumes" ||
    pathname === "/job-descriptions" ||
    /^\/(?:resumes|job-descriptions)\/[^/]+$/.test(pathname)
  );
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, frontendRoot, "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8080";
  const proxy: Record<string, ProxyOptions> = Object.fromEntries(
    apiPaths.map((apiPath) => [
      apiPath,
      {
        target: apiTarget,
        changeOrigin: true,
        bypass: (request) =>
          isSpaNavigationRequest(
            request.method,
            request.url,
            request.headers.accept,
            typeof request.headers["content-type"] === "string"
              ? request.headers["content-type"]
              : undefined,
            typeof request.headers["sec-fetch-dest"] === "string"
              ? request.headers["sec-fetch-dest"]
              : undefined,
            typeof request.headers["sec-fetch-mode"] === "string"
              ? request.headers["sec-fetch-mode"]
              : undefined,
          )
            ? request.url
            : undefined,
      },
    ])
  );

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": frontendRoot,
      },
    },
    server: {
      host: "127.0.0.1",
      port: 3000,
      strictPort: false,
      proxy,
    },
    preview: {
      host: "127.0.0.1",
      port: 4173,
      strictPort: false,
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
