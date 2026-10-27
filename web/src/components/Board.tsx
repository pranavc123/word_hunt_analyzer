// 4×4 board with an original tile style; draws a path as an arrowed polyline (S4.T4).

const SIZE = 400;
const GAP = 12;
const TILE = (SIZE - GAP * 5) / 4;

export type TileMark = "low" | "found" | "missed" | "wasted";

export function tileCenter(i: number): [number, number] {
  const r = Math.floor(i / 4);
  const c = i % 4;
  return [GAP + c * (TILE + GAP) + TILE / 2, GAP + r * (TILE + GAP) + TILE / 2];
}

export interface BoardProps {
  letters: string | null;
  path?: number[] | null;
  pathKind?: "found" | "missed" | "wasted";
  marks?: Partial<Record<number, TileMark>>;
  selected?: number | null;
  onTileClick?: (i: number) => void;
  label?: string;
}

export function Board({ letters, path, pathKind = "found", marks = {}, selected, onTileClick, label }: BoardProps) {
  const onPath = new Set(path ?? []);
  const points = (path ?? []).map((i) => tileCenter(i).join(",")).join(" ");
  return (
    <svg
      className={`board board--${pathKind}`}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      role="img"
      aria-label={label ?? (letters ? `Board ${letters}` : "Board with unknown letters")}
    >
      <defs>
        <marker id="wh-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="5" markerHeight="5" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" className="board__arrowhead" />
        </marker>
      </defs>
      <rect className="board__bg" x="0" y="0" width={SIZE} height={SIZE} rx="22" />
      {Array.from({ length: 16 }, (_, i) => {
        const [cx, cy] = tileCenter(i);
        const mark = marks[i];
        const classes = ["tile", onPath.has(i) && "tile--on-path", mark && `tile--${mark}`, selected === i && "tile--selected"]
          .filter(Boolean)
          .join(" ");
        return (
          <g
            key={i}
            className={classes}
            data-testid={`tile-${i}`}
            onClick={onTileClick ? () => onTileClick(i) : undefined}
            role={onTileClick ? "button" : undefined}
            aria-label={onTileClick ? `Tile ${i + 1}: ${letters?.[i] ?? "unknown"}` : undefined}
          >
            <rect x={cx - TILE / 2} y={cy - TILE / 2} width={TILE} height={TILE} rx="16" />
            <title>{letters?.[i] ?? "?"}</title>
          </g>
        );
      })}
      {/* the path sits between the tiles and the letters, so letters stay readable */}
      {path && path.length > 1 && (
        <polyline className="board__path" points={points} markerEnd="url(#wh-arrow)" data-testid="path" />
      )}
      {path && path.length > 0 && (
        <circle className="board__start" cx={tileCenter(path[0])[0]} cy={tileCenter(path[0])[1]} r="10" />
      )}
      {Array.from({ length: 16 }, (_, i) => {
        const [cx, cy] = tileCenter(i);
        return (
          <text key={i} className="tile__letter" x={cx} y={cy + 4} textAnchor="middle" dominantBaseline="middle">
            {letters?.[i] ?? "?"}
          </text>
        );
      })}
    </svg>
  );
}
