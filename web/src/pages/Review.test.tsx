import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import board from "../test/fixtures/board_verified.json";
import { renderRoute } from "../test/render";
import { GameReview } from "./GameReview";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const open = () => renderRoute(<GameReview />, "/boards/:id", `/boards/${board.id}`, { [`/v1/boards/${board.id}`]: board });

describe("Game review", () => {
  it("shows the score headline and found words; tapping a word draws its path", async () => {
    open();
    const found = board.words.filter((w) => w.found);
    expect(await screen.findByText(new RegExp(`${found.length} words found`))).toBeInTheDocument();
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getAllByRole("button")).toHaveLength(found.length);
    const first = within(panel).getAllByRole("button")[0];
    fireEvent.click(first);
    const path = screen.getByTestId("path");
    const word = found.sort((a, b) => (a.found_at_ms ?? 0) - (b.found_at_ms ?? 0))[0];
    expect(path.getAttribute("points")!.split(" ")).toHaveLength(word.path.length);
  });

  it("lists missed words by points and wasted time", async () => {
    open();
    fireEvent.click(await screen.findByRole("tab", { name: /Missed/ }));
    const rows = within(screen.getByRole("tabpanel")).getAllByRole("button");
    const missed = board.words.filter((w) => !w.found && w.in_base).sort((a, b) => b.points - a.points);
    expect(rows).toHaveLength(missed.length);
    expect(rows[0]).toHaveTextContent(missed[0].word.toUpperCase());
    fireEvent.click(screen.getByRole("tab", { name: /Wasted/ }));
    const wasted = board.attempts.filter((a) => a.result !== "valid_new");
    expect(within(screen.getByRole("tabpanel")).getAllByRole("button")).toHaveLength(wasted.length);
  });

  it("scrubs through attempts in time order", async () => {
    open();
    const slider = await screen.findByLabelText("Replay position");
    fireEvent.change(slider, { target: { value: "0" } });
    expect(screen.getByTestId("path")).toBeInTheDocument();
  });
});
