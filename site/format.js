// The pure formatting the pages share; the bands mirror manc.queries.

export const BANDS = ["headwind", "lean_against", "neutral", "lean_for", "tailwind"];
const DASH = "—";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const IMPORTANCE = { 1: "low", 2: "medium", 3: "high" };

export function bandLabel(band) {
  return band.replaceAll("_", " ");
}

export function formatScore(score) {
  return score === null || score === undefined ? DASH : String(Math.round(score));
}

export function formatDelta(delta) {
  if (delta === null || delta === undefined) return DASH;
  const fixed = delta.toFixed(1);
  return delta > 0 ? `+${fixed}` : fixed;
}

export function formatPercent(ratio) {
  if (ratio === null || ratio === undefined) return DASH;
  const fixed = (ratio * 100).toFixed(1);
  return ratio > 0 ? `+${fixed}%` : `${fixed}%`;
}

export function formatNumber(value) {
  if (value === null || value === undefined) return DASH;
  return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

export function formatCompact(value) {
  if (value === null || value === undefined) return DASH;
  const magnitude = Math.abs(value);
  if (magnitude >= 1e9) return `${(value / 1e9).toLocaleString("en-US", { maximumFractionDigits: 2 })}bn`;
  if (magnitude >= 1e6) return `${(value / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 })}M`;
  if (magnitude >= 1e4) return `${Math.round(value / 1e3).toLocaleString("en-US")}k`;
  if (magnitude >= 100) return Math.round(value).toLocaleString("en-US");
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export function formatDate(value) {
  if (!value) return DASH;
  const [year, month, day] = value.slice(0, 10).split("-");
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}

export function importanceLabel(importance) {
  return IMPORTANCE[importance] ?? String(importance);
}
