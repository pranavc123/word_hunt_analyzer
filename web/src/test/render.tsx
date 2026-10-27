import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

/** Render at `path` with routes; fetch answers from `responses` (path → JSON). */
export function renderRoute(ui: React.ReactElement, pattern: string, path: string, responses: Record<string, unknown> = {}) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      calls.push({ url, init });
      const key = Object.keys(responses).find((k) => new URL(url).pathname === k);
      if (!key) return new Response("{}", { status: 404 });
      return new Response(JSON.stringify(responses[key]), { headers: { "Content-Type": "application/json" } });
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...utils, calls };
}
