// The asset page's pure helpers: range, TradingView embed, report parsing, table rows.
import type { AssetHistory, CalendarEvent, ForecastPanel, ForecastRow, HeadlineView, MacroForecastRow } from "../api/types";
import { DASH, formatDate, formatNumber, formatPercent, isoDay, shiftDays, words } from "./format";

export const RANGE_PRESETS = [30, 90, 180, 365] as const;
export const EVENTS_AHEAD_DAYS = 14;

export function rangeFor(days: number, today: string = isoDay(new Date())): { from: string; to: string } {
  return { from: shiftDays(today, -days), to: today };
}

export function tradingViewUrl(symbol: string | null | undefined, theme: string): string | null {
  // TradingView's own widget iframe, daily candles, no toolbar: the price next to the score.
  if (!symbol) return null;
  const params = new URLSearchParams({
    symbol,
    interval: "D",
    theme,
    style: "1",
    locale: "en",
    timezone: "Etc/UTC",
    hide_top_toolbar: "1",
    hidesidetoolbar: "1",
    symboledit: "0",
    saveimage: "0",
    withdateranges: "1",
    hideideas: "1",
  });
  return `https://s.tradingview.com/widgetembed/?${params}`;
}

export function eventsFor(events: CalendarEvent[], economies: string[], today: string, days = EVENTS_AHEAD_DAYS): CalendarEvent[] {
  const end = shiftDays(today, days);
  return events.filter((event) => {
    const day = event.date.slice(0, 10);
    return economies.includes(event.country) && day > today && day <= end;
  });
}

export interface ReportParts {
  title: string;
  summary: string;
  model: string;
  rest: string;
}

export function reportParts(markdown: string | null | undefined): ReportParts {
  const parts: ReportParts = { title: "", summary: "", model: "", rest: "" };
  if (!markdown) return parts;
  const footer = markdown.match(/\n---\n\nSummary by (.+?)\.\n?$/);
  const body = footer ? markdown.slice(0, footer.index) : markdown;
  parts.model = footer?.[1] ?? "";
  const firstSection = body.indexOf("\n## ");
  const head = firstSection === -1 ? body : body.slice(0, firstSection);
  parts.rest = firstSection === -1 ? "" : body.slice(firstSection + 1).trim();
  const [title = "", ...paragraphs] = head.split("\n\n");
  parts.title = title.replace(/^#\s*/, "").trim();
  parts.summary = paragraphs.join("\n\n").trim();
  return parts;
}

export function reportDay(history: AssetHistory | null | undefined, today: string): string {
  return history?.points?.at(-1)?.date ?? today;
}

export interface HeadlineRow {
  title: string;
  url: string;
  source: string;
  date: string;
  direction: number;
  glyph: string;
  weight: string;
  confidence: string;
  bar: number;
}

export function headlineRows(headlines: HeadlineView[]): HeadlineRow[] {
  const strongest = Math.max(0, ...headlines.map((headline) => headline.weight));
  return headlines.map((headline) => ({
    title: headline.title,
    url: headline.url,
    source: headline.source,
    date: formatDate(headline.published_at),
    direction: headline.direction,
    glyph: headline.direction > 0 ? "▲" : "▼",
    weight: headline.weight.toFixed(2),
    confidence: headline.confidence.toFixed(2),
    bar: strongest > 0 ? (100 * headline.weight) / strongest : 0,
  }));
}

export function revision(row: { value: number; previous_value: number | null }): string {
  if (row.previous_value === null || row.previous_value === undefined) return DASH;
  if (row.value > row.previous_value) return "▲";
  if (row.value < row.previous_value) return "▼";
  return DASH;
}

export interface ForecastTableRow {
  key: string;
  horizon: string;
  horizonDate: string;
  institution: string;
  value: string;
  vsSpot: string;
  revision: string;
  previous: string;
  published: string;
  confidence: string;
  median: boolean;
}

export function forecastRows(panel: ForecastPanel): ForecastTableRow[] {
  // One flat list for the table: the rows of a horizon, then its median, horizons in date order.
  const byHorizon = new Map<string, ForecastRow[]>();
  for (const row of panel.rows) {
    byHorizon.set(row.horizon_date, [...(byHorizon.get(row.horizon_date) ?? []), row]);
  }
  const medians = new Map(panel.medians.map((median) => [median.horizon_date, median.value]));
  const rows: ForecastTableRow[] = [];
  for (const horizon of [...byHorizon.keys()].sort()) {
    const group = byHorizon.get(horizon) ?? [];
    const label = group[0]?.horizon_label ?? horizon;
    for (const row of group) {
      rows.push({
        key: `${horizon}:${row.institution}`,
        horizon: label,
        horizonDate: formatDate(horizon),
        institution: words(row.institution),
        value: formatNumber(row.value),
        vsSpot: formatPercent(row.vs_spot),
        revision: revision(row),
        previous: formatNumber(row.previous_value),
        published: formatDate(row.published_at),
        confidence: row.confidence.toFixed(2),
        median: false,
      });
    }
    const median = medians.get(horizon);
    if (median !== undefined) {
      rows.push({
        key: `${horizon}:median`,
        horizon: label,
        horizonDate: formatDate(horizon),
        institution: "median",
        value: formatNumber(median),
        vsSpot: panel.spot ? formatPercent(median / panel.spot - 1) : DASH,
        revision: "",
        previous: "",
        published: "",
        confidence: "",
        median: true,
      });
    }
  }
  return rows;
}

export interface MacroTableRow {
  key: string;
  economy: string;
  metric: string;
  horizon: string;
  horizonDate: string;
  institution: string;
  value: string;
  revision: string;
  previous: string;
  published: string;
}

export function macroRows(rows: MacroForecastRow[]): MacroTableRow[] {
  return rows.map((row) => ({
    key: `${row.institution}:${row.economy}:${row.metric}:${row.horizon_date}`,
    economy: words(row.economy),
    metric: words(row.metric),
    horizon: row.horizon_label,
    horizonDate: formatDate(row.horizon_date),
    institution: words(row.institution),
    value: formatNumber(row.value),
    revision: revision(row),
    previous: formatNumber(row.previous_value),
    published: formatDate(row.published_at),
  }));
}
