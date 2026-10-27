// Response shapes of server/app/api_read.py (the FastAPI handlers return plain dicts).

export type ReviewStatus = "pending" | "needs_letter_fix" | "needs_review" | "verified" | "skipped";

export interface BoardRow {
  id: string;
  seq: number;
  status: "played" | "skipped";
  review_status: ReviewStatus;
  letters: string | null;
  opened_at: string;
  view_ms: number;
  final_score: number | null;
  final_word_count: number | null;
  extracted_score: number | null;
  max_points: number | null;
  solver_words: number | null;
  fixes: string[];
  all_words_status: string;
}

export interface SessionSummary {
  id: string;
  started_at: string;
  device: string;
  board_count: number;
  played_count: number;
  keep_rate: number;
  count_30k: number;
  skip_seconds: number;
  verified_count: number;
  needs_review: number;
  needs_letter_fix: number;
  best_board: BoardRow | null;
  biggest_miss: { word: string; points: number; board_id: string } | null;
  score_by_position: { seq: number; score: number | null }[];
  boards?: BoardRow[];
}

export interface Attempt {
  seq: number;
  t_start_ms: number;
  t_end_ms: number;
  tiles_seen: number[];
  path: number[] | null;
  word: string | null;
  result: "valid_new" | "already_found" | "not_a_word";
  points: number;
}

export interface BoardWord {
  word: string;
  path: number[];
  points: number;
  found: boolean;
  found_at_ms: number | null;
  in_enable: boolean;
  in_base: boolean;
}

export interface BoardDetail extends BoardRow {
  session_id: string;
  letters_conf: number[] | null;
  letters_confirmed: boolean;
  end_visible_words: string[] | null;
  reconciled: boolean;
  error: string | null;
  images: { board: string | null; end_banner: string | null; end_list: string | null };
  attempts: Attempt[];
  words: BoardWord[];
  all_words: { status: string; counts_by_length: Record<string, number>; revealed: string[] } | null;
  prev_id: string | null;
  next_id: string | null;
}
