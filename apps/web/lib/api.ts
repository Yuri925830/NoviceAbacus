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
    if (Array.isArray(error.detail) && error.detail.length) {
      const issue = error.detail[0] as {loc?: unknown[]; msg?: string; type?: string};
      const field = String(issue.loc?.at(-1) || "这个字段");
      const labels: Record<string, string> = {
        monthly_income_cny: "每月固定收入",
        monthly_essential_expenses_cny: "每月必要生活费",
        monthly_current_expenses_cny: "维持当前生活的总开销",
        emergency_months: "应急金月数",
        amount_cny: "金额",
        target_cny: "目标金额",
      };
      const reason = issue.type?.includes("greater_than") ? "需要填写一个大于 0 的数字" : "填写的数字或格式不正确";
      return `${labels[field] || field}${reason}`;
    }
  }
  return error instanceof Error ? error.message : "操作失败，请稍后重试";
}
