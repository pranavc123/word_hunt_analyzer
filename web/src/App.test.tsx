import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import sessions from "./test/fixtures/sessions.json";

function renderAt(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const body = url.includes("/v1/sessions") ? sessions : { ok: true, version: "9.9" };
      return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App shell", () => {
  it("shows five nav items and the sessions list", async () => {
    renderAt("/");
    expect(screen.getByRole("navigation", { name: "Main" }).querySelectorAll("a")).toHaveLength(5);
    expect(await screen.findByText(/Last session:/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /boards ·/ })).toHaveLength(sessions.length);
  });

  it("navigates with the bottom nav", () => {
    renderAt("/");
    fireEvent.click(screen.getByRole("link", { name: /Dictionary/ }));
    expect(screen.getByRole("heading", { name: "Dictionary" })).toBeInTheDocument();
  });

  it("settings shows server health and saves the token", async () => {
    renderAt("/settings");
    expect(await screen.findByText(/reachable \(v9\.9\)/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Access token/), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Save token" }));
    expect(localStorage.getItem("wh-token")).toBe("secret");
  });
});
