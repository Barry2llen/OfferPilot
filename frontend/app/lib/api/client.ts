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

  return normalizeBaseUrl(
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"
  );
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

  const res = await fetch(url, {
    headers: isFormData
      ? { ...(options.headers as Record<string, string> | undefined) }
      : {
          "Content-Type": "application/json",
          ...(options.headers as Record<string, string> | undefined),
        },
    ...options,
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
