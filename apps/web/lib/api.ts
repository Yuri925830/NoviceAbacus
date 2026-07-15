export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

const configuredApiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

export function apiUrl(path: string): string {
  return `${configuredApiBase || "/backend"}${path}`;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response = await fetch(apiUrl(path), {...options, headers, credentials: "include", cache: "no-store"});
  if (response.status === 401 && path !== "/auth/refresh" && path !== "/auth/login") {
    const refreshed = await fetch(apiUrl("/auth/refresh"), {method: "POST", credentials: "include", cache: "no-store"});
    if (refreshed.ok) response = await fetch(apiUrl(path), {...options, headers, credentials: "include", cache: "no-store"});
  }
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try { const payload = await response.json(); detail = payload.detail ?? payload; } catch {}
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function money(value: string | number | null | undefined, hidden = false): string {
  if (hidden) return "••••••";
  const amount = Number(value ?? 0);
  return new Intl.NumberFormat("zh-CN", {style: "currency", currency: "CNY", maximumFractionDigits: 2}).format(amount);
}

export function percent(value: string | number | null | undefined): string {
  return `${Number(value ?? 0).toFixed(1)}%`;
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}).format(new Date(value));
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") return error.detail;
    if (error.detail && typeof error.detail === "object" && "message" in error.detail) return String((error.detail as {message: unknown}).message);
  }
  return error instanceof Error ? error.message : "操作失败，请稍后重试";
}
