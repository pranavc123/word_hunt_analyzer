import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function renderAt(path: string) {
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
  it("shows five nav items and the sessions page", () => {
    renderAt("/");
    expect(screen.getAllByRole("link")).toHaveLength(5);
    expect(screen.getByRole("heading", { name: "Sessions" })).toBeInTheDocument();
  });

  it("navigates with the bottom nav", () => {
    renderAt("/");
    fireEvent.click(screen.getByRole("link", { name: /Dictionary/ }));
    expect(screen.getByRole("heading", { name: "Dictionary" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Dictionary/ })).toHaveClass("active");
  });

  it("settings shows server health from the typed client", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ ok: true, version: "9.9" }), {
        headers: { "Content-Type": "application/json" },
      })),
    );
    renderAt("/settings");
    expect(await screen.findByText(/reachable \(v9\.9\)/)).toBeInTheDocument();
  });
});
