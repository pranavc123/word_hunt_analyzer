import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import board from "../test/fixtures/board_letter_fix.json";
import session from "../test/fixtures/session.json";
import { renderRoute } from "../test/render";
import { BoardConfirm } from "./BoardConfirm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Board confirm", () => {
  it("lets you type the letters tile by tile and saves them", async () => {
    const answer = "ABCDEFGHIJKLMNOP";
    const { calls } = renderRoute(<BoardConfirm />, "/sessions/:id/confirm", `/sessions/${session.id}/confirm`, {
      [`/v1/sessions/${session.id}`]: session,
      [`/v1/boards/${board.id}`]: board,
      [`/v1/boards/${board.id}/letters`]: { ...board, letters: answer, review_status: "skipped" },
    });
    const save = await screen.findAllByRole("button", { name: "Save letters" });
    expect(save[0]).toBeDisabled(); // unknown letters
    fireEvent.click(screen.getAllByRole("button", { name: /Tile 1:/ })[0]); // selects letter 1 in the field
    const field = screen.getAllByLabelText(/Letters, row by row/)[0];
    fireEvent.change(field, { target: { value: answer.toLowerCase() } });
    expect(screen.getAllByRole("button", { name: /Tile 16: P/ })).toHaveLength(1); // board follows the field
    const button = screen.getAllByRole("button", { name: "Save letters" })[0];
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(calls.some((c) => c.init?.method === "PATCH")).toBe(true));
    const patch = calls.find((c) => c.init?.method === "PATCH")!;
    expect(JSON.parse(String(patch.init!.body))).toEqual({ letters: answer });
    expect(await screen.findByText(/Saved/)).toBeInTheDocument();
  });
});
