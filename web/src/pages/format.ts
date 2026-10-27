export const n = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString("en-US"));
export const pct = (v: number) => `${Math.round(v * 100)}%`;
export const secs = (ms: number) => `${(ms / 1000).toFixed(1)}s`;
export const when = (iso: string) =>
  new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export const STATUS_LABEL: Record<string, string> = {
  verified: "verified",
  needs_review: "needs review",
  needs_letter_fix: "fix letters",
  pending: "processing",
  skipped: "skipped",
};
