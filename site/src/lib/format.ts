// The pure formatting the pages share; the bands mirror manc.queries.

export const BANDS = ["headwind", "lean_against", "neutral", "lean_for", "tailwind"] as const;
export type Band = (typeof BANDS)[number];
export const DASH = "—";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const IMPORTANCE: Record<number, string> = { 1: "low", 2: "medium", 3: "high" };

type Maybe = number | null | undefined;

export function bandLabel(band: string): string {
  return band.replaceAll("_", " ");
}

export function words(identifier: string): string {
  return identifier.replaceAll("_", " ");
}

export function formatScore(score: Maybe): string {
  return score === null || score === undefined ? DASH : String(Math.round(score));
}

export function formatDelta(delta: Maybe): string {
  if (delta === null || delta === undefined) return DASH;
  const fixed = delta.toFixed(1);
  return delta > 0 ? `+${fixed}` : fixed;
}

export function formatPercent(ratio: Maybe): string {
  if (ratio === null || ratio === undefined) return DASH;
  const fixed = (ratio * 100).toFixed(1);
  return ratio > 0 ? `+${fixed}%` : `${fixed}%`;
}

export function formatNumber(value: Maybe): string {
  if (value === null || value === undefined) return DASH;
  return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

export function formatCompact(value: Maybe): string {
  if (value === null || value === undefined) return DASH;
  const magnitude = Math.abs(value);
  if (magnitude >= 1e9) return `${(value / 1e9).toLocaleString("en-US", { maximumFractionDigits: 2 })}bn`;
  if (magnitude >= 1e6) return `${(value / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 })}M`;
  if (magnitude >= 1e4) return `${Math.round(value / 1e3).toLocaleString("en-US")}k`;
  if (magnitude >= 100) return Math.round(value).toLocaleString("en-US");
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return DASH;
  const [year, month, day] = value.slice(0, 10).split("-");
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}

export function importanceLabel(importance: number): string {
  return IMPORTANCE[importance] ?? String(importance);
}

export function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function shiftDays(iso: string, days: number): string {
  return isoDay(new Date(new Date(`${iso}T00:00:00Z`).getTime() + days * 24 * 60 * 60 * 1000));
}
