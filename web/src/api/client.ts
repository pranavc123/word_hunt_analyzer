import createClient from "openapi-fetch";
import { useEffect, useState } from "react";
import type { components, paths } from "./schema";

export type Health = components["schemas"]["Health"];

const BASE = import.meta.env.VITE_API_BASE ?? globalThis.location?.origin ?? "";
const TOKEN_KEY = "wh-token";

// Same-origin by default (the server also serves this app); override with VITE_API_BASE.
export const api = createClient<paths>({
  baseUrl: BASE,
  fetch: (req) => globalThis.fetch(req), // resolved per call so tests can stub fetch
});

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token.trim());
  } catch {
    /* private mode: the token lasts for this page only */
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await globalThis.fetch(new URL(path, BASE || "http://localhost").toString(), { ...init, headers });
  if (!res.ok) throw new ApiError(res.status, res.status === 401 ? "Add your token in Settings" : `HTTP ${res.status}`);
  return (await res.json()) as T;
}

export const apiGet = <T>(path: string) => request<T>(path);

export const apiPatch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });

export async function getHealth(): Promise<Health> {
  const { data, error } = await api.GET("/v1/health");
  if (error || !data) throw new Error("server unreachable");
  return data;
}

/** Images need the bearer token, so fetch them and show a blob URL. */
export function useAuthedImage(path: string | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    let objectUrl: string | null = null;
    const token = getToken();
    globalThis
      .fetch(new URL(path, BASE || "http://localhost").toString(), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => {
        if (b && alive && typeof URL.createObjectURL === "function") {
          objectUrl = URL.createObjectURL(b);
          setUrl(objectUrl);
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);
  return url;
}
