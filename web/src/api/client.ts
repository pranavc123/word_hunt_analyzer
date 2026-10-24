import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Health = components["schemas"]["Health"];

// Same-origin by default (Vite proxies /v1 in dev); override with VITE_API_BASE.
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE ?? globalThis.location?.origin ?? "",
  fetch: (req) => globalThis.fetch(req), // resolved per call so tests can stub fetch
});

export async function getHealth(): Promise<Health> {
  const { data, error } = await api.GET("/v1/health");
  if (error || !data) throw new Error("server unreachable");
  return data;
}
