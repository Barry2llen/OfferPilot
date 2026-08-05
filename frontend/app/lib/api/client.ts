import { getCurrentLocale } from "@/app/lib/i18n";

declare global {
  interface Window {
    offerPilotRuntime?: {
      apiBaseUrl?: string;
    };
  }
}

function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function getBaseUrl(): string {
  if (typeof window !== "undefined") {
    const runtimeBaseUrl = window.offerPilotRuntime?.apiBaseUrl;
    if (runtimeBaseUrl) {
      return normalizeBaseUrl(runtimeBaseUrl);
    }
  }

  return normalizeBaseUrl(import.meta.env.VITE_API_URL || "");
}

export class ApiError extends Error {
  public status: number;
  public detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const isFormData = options.body instanceof FormData;
  const { headers: optionHeaders, ...requestOptions } = options;

  const res = await fetch(url, {
    ...requestOptions,
    headers: isFormData
      ? {
          ...(optionHeaders as Record<string, string> | undefined),
          "Accept-Language": getCurrentLocale(),
        }
      : {
          ...(optionHeaders as Record<string, string> | undefined),
          "Content-Type": "application/json",
          Accept: "application/json",
          "Accept-Language": getCurrentLocale(),
        },
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // use statusText
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export function apiUrl(path: string): string {
  return `${getBaseUrl()}${path}`;
}

export function localeHeaders(): Record<string, string> {
  return { "Accept-Language": getCurrentLocale() };
}
