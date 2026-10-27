import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import session from "../test/fixtures/session.json";
import { renderRoute } from "../test/render";
import { SessionSummary } from "./SessionSummary";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Session summary", () => {
  it("renders headline, stats, best board, biggest miss and the letter-fix link", async () => {
    renderRoute(<SessionSummary />, "/sessions/:id", `/sessions/${session.id}`, { [`/v1/sessions/${session.id}`]: session });
    expect(await screen.findByText(new RegExp(`${session.played_count} of ${session.board_count} boards played`))).toBeInTheDocument();
    expect(screen.getByText("Boards seen").previousSibling).toHaveTextContent(String(session.board_count));
    expect(screen.getByText("Best board")).toBeInTheDocument();
    expect(screen.getByText(session.biggest_miss!.word.toUpperCase(), { exact: false })).toBeInTheDocument();
    const fix = screen.getByRole("link", { name: /need letters checked/ });
    expect(fix.getAttribute("href")).toBe(`/sessions/${session.id}/confirm`);
    expect(screen.getAllByRole("link", { name: /^#\d/ })).toHaveLength(session.board_count);
  });
});
