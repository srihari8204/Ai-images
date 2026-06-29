// Typed API client with bearer-token auth and transparent refresh-on-401.
//
// Tokens live in localStorage (SPA). On a 401 the client attempts a single
// refresh using the rotating refresh token, then retries the original request.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080";

const ACCESS_KEY = "aim_access";
const REFRESH_KEY = "aim_refresh";

export function getAccess(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}
export function getRefresh(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}
export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function rawRequest(path: string, init: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, init);
}

async function refreshTokens(): Promise<boolean> {
  const refresh = getRefresh();
  if (!refresh) return false;
  const resp = await rawRequest("/api/v1/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!resp.ok) {
    clearTokens();
    return false;
  }
  const data = await resp.json();
  setTokens(data.access_token, data.refresh_token);
  return true;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  auth?: boolean;
  idempotencyKey?: string;
  raw?: boolean;
}

export async function api<T = any>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {}, auth = true, idempotencyKey } = opts;

  const buildHeaders = (): Record<string, string> => {
    const h: Record<string, string> = { ...headers };
    if (body !== undefined && !(body instanceof FormData)) {
      h["Content-Type"] = "application/json";
    }
    if (idempotencyKey) h["Idempotency-Key"] = idempotencyKey;
    const token = getAccess();
    if (auth && token) h["Authorization"] = `Bearer ${token}`;
    return h;
  };

  const send = () =>
    rawRequest(path, {
      method,
      headers: buildHeaders(),
      body:
        body === undefined
          ? undefined
          : body instanceof FormData
          ? body
          : JSON.stringify(body),
    });

  let resp = await send();

  if (resp.status === 401 && auth && getRefresh()) {
    if (await refreshTokens()) {
      resp = await send();
    }
  }

  if (resp.status === 204) return undefined as T;

  const text = await resp.text();
  const data = text ? JSON.parse(text) : null;

  if (!resp.ok) {
    const err = data?.error ?? {};
    throw new ApiError(
      resp.status,
      err.code ?? "error",
      err.message ?? resp.statusText,
      err.details
    );
  }
  return data as T;
}
