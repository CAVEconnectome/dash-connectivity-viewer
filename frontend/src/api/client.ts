// Tiny fetch wrapper:
//   - Sends `credentials: "include"` so the middle-auth cookie rides along.
//   - Optionally attaches a localStorage Bearer token (paste-once API path).
//   - Throws an ApiError-shaped Error so TanStack Query surfaces a useful message.

import type { ApiError } from "./types";

const TOKEN_STORAGE_KEY = "dcv:auth_token";

export function setAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export class ApiCallError extends Error {
  status: number;
  body: ApiError | null;
  constructor(status: number, body: ApiError | null) {
    super(body?.message ?? `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  query?: Record<string, string | number | undefined | null>;
  signal?: AbortSignal;
}

export async function apiFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getAuthToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let url = path;
  if (opts.query) {
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== null && v !== "") search.set(k, String(v));
    }
    const qs = search.toString();
    if (qs) url += `?${qs}`;
  }
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(url, {
    method: opts.method ?? "GET",
    headers,
    credentials: "include",
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
  if (!resp.ok) {
    let body: ApiError | null = null;
    try {
      body = await resp.json();
    } catch {
      // ignore
    }
    throw new ApiCallError(resp.status, body);
  }
  return resp.json() as Promise<T>;
}
