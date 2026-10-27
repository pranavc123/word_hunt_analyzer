import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Board, tileCenter } from "./Board";

afterEach(cleanup);

describe("Board", () => {
  it("draws 16 tiles with their letters", () => {
    render(<Board letters="LCMEORSIETRATDIM" />);
    expect(screen.getAllByTestId(/^tile-/)).toHaveLength(16);
    expect(screen.getByTestId("tile-0")).toHaveTextContent("L"); // the tile's <title>
    expect(screen.getByTestId("tile-15")).toHaveTextContent("M");
  });

  it("draws a path through tile centres with an arrow", () => {
    render(<Board letters="LCMEORSIETRATDIM" path={[1, 4, 9]} />);
    const line = screen.getByTestId("path");
    expect(line.getAttribute("points")).toBe([1, 4, 9].map((i) => tileCenter(i).join(",")).join(" "));
    expect(line.getAttribute("marker-end")).toBe("url(#wh-arrow)");
    expect(screen.getByTestId("tile-4").getAttribute("class")).toContain("tile--on-path");
  });

  it("marks uncertain tiles and reports clicks", () => {
    const onClick = vi.fn();
    render(<Board letters={null} marks={{ 3: "low" }} onTileClick={onClick} />);
    expect(screen.getByTestId("tile-3").getAttribute("class")).toContain("tile--low");
    expect(screen.getByTestId("tile-0")).toHaveTextContent("?");
    fireEvent.click(screen.getByRole("button", { name: /Tile 4/ }));
    expect(onClick).toHaveBeenCalledWith(3);
  });
});
