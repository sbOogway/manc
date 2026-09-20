import { expect, test } from "vitest";

import type { CalendarEvent, ForecastPanel } from "../api/types";
import {
  eventsFor,
  forecastRows,
  headlineRows,
  macroRows,
  rangeFor,
  reportDay,
  reportParts,
  revision,
  tradingViewUrl,
} from "../lib/asset";
import { themeName } from "../lib/theme";

function event(overrides: Partial<CalendarEvent>): CalendarEvent {
  return { id: "x", date: "2026-09-20T12:00:00Z", country: "united_states", event: "CPI", category: "inflation", importance: 3, consensus: null, previous: null, actual: null, ...overrides };
}

test("rangeFor gives ISO from/to for every preset", () => {
  expect(rangeFor(30, "2026-09-19")).toEqual({ from: "2026-08-20", to: "2026-09-19" });
  expect(rangeFor(365, "2026-09-19")).toEqual({ from: "2025-09-19", to: "2026-09-19" });
});

test("eventsFor keeps the asset's economies in the window, in order", () => {
  const events = [
    event({ id: "past", date: "2026-09-18T12:00:00Z" }),
    event({ id: "soon", date: "2026-09-20T12:00:00Z", country: "euro_area", importance: 2 }),
    event({ id: "other", date: "2026-09-21T12:00:00Z", country: "japan" }),
    event({ id: "later", date: "2026-09-30T12:00:00Z" }),
    event({ id: "far", date: "2026-10-10T12:00:00Z" }),
  ];
  expect(eventsFor(events, ["euro_area", "united_states"], "2026-09-19", 14).map((one) => one.id)).toEqual(["soon", "later"]);
});

const PANEL: ForecastPanel = {
  symbol: "EURUSD",
  as_of: "2026-09-19",
  rows: [
    { institution: "goldman_sachs", horizon_date: "2026-12-31", horizon_label: "year-end", value: 1.2, previous_value: 1.1, vs_spot: 0.05, published_at: "2026-09-17T10:00:00Z", confidence: 0.9 },
    { institution: "goldman_sachs", horizon_date: "2027-06-30", horizon_label: "12 months", value: 1.25, previous_value: null, vs_spot: 0.09, published_at: "2026-09-17T10:00:00Z", confidence: 0.9 },
    { institution: "ing", horizon_date: "2026-12-31", horizon_label: "year-end", value: 1.15, previous_value: 1.18, vs_spot: 0.0, published_at: "2026-09-18T10:00:00Z", confidence: 0.7 },
  ],
  medians: [
    { horizon_date: "2026-12-31", value: 1.175 },
    { horizon_date: "2027-06-30", value: 1.25 },
  ],
  macro: [],
  spot: 1.1479,
};

test("forecastRows lists each horizon's rows then its median, horizons in date order", () => {
  const rows = forecastRows(PANEL);
  expect(rows.map((row) => [row.horizon, row.institution])).toEqual([
    ["year-end", "goldman sachs"],
    ["year-end", "ing"],
    ["year-end", "median"],
    ["12 months", "goldman sachs"],
    ["12 months", "median"],
  ]);
  expect(rows[2]?.median).toBe(true);
  expect(rows[2]?.value).toBe("1.175");
  expect(rows[2]?.vsSpot).toBe("+2.4%");
  expect(rows[0]?.vsSpot).toBe("+5.0%");
  expect(rows.map((row) => row.revision)).toEqual(["▲", "▼", "", "—", ""]);
  expect(rows[0]?.published).toBe("17 Sep 2026");
  expect(rows[0]?.horizonDate).toBe("31 Dec 2026");
});

test("forecastRows without a spot leaves the median distance blank", () => {
  const rows = forecastRows({ ...PANEL, rows: [PANEL.rows[2]!], medians: [PANEL.medians[0]!], spot: null });
  expect(rows[1]?.vsSpot).toBe("—");
});

test("macroRows flattens the macro forecasts with words for identifiers", () => {
  const [row] = macroRows([
    { institution: "goldman_sachs", economy: "united_states", metric: "policy_rate", horizon_date: "2026-12-31", horizon_label: "year-end", value: 3.4, previous_value: 3.6, published_at: "2026-09-17T10:00:00Z", confidence: 0.8 },
  ]);
  expect(row?.economy).toBe("united states");
  expect(row?.metric).toBe("policy rate");
  expect(row?.revision).toBe("▼");
  expect(row?.value).toBe("3.4");
});

test("revision arrows", () => {
  expect(revision({ value: 1.2, previous_value: 1.1 })).toBe("▲");
  expect(revision({ value: 1.0, previous_value: 1.1 })).toBe("▼");
  expect(revision({ value: 1.1, previous_value: 1.1 })).toBe("—");
  expect(revision({ value: 1.1, previous_value: null })).toBe("—");
});

test("headlineRows scales the weight bars to the strongest headline, in API order", () => {
  const rows = headlineRows([
    { title: "a", url: "u/a", source: "reuters", published_at: "2026-09-18T10:00:00Z", direction: -1, confidence: 0.8, source_weight: 1.0, weight: 0.8 },
    { title: "b", url: "u/b", source: "fxstreet", published_at: "2026-09-18T09:00:00Z", direction: 1, confidence: 0.9, source_weight: 0.6, weight: 0.54 },
    { title: "c", url: "u/c", source: "blog", published_at: "2026-09-17T09:00:00Z", direction: 1, confidence: 0.2, source_weight: 1.0, weight: 0.2 },
  ]);
  expect(rows.map((row) => row.bar)).toEqual([100, 67.5, 25]);
  expect(rows.map((row) => row.weight)).toEqual(["0.80", "0.54", "0.20"]);
  expect(rows.map((row) => row.glyph)).toEqual(["▼", "▲", "▲"]);
  expect(rows[0]?.date).toBe("18 Sep 2026");
  expect(headlineRows([])).toEqual([]);
});

test("reportDay is the last scored day, or today without scores", () => {
  const history = { symbol: "EURUSD", formula: "v2", scale: { low: -100, high: 100, neutral: 0, edges: [-40, -10, 10, 40] as [number, number, number, number] }, points: [{ date: "2026-09-17", score: 1, band: "neutral", components: {}, n_news: 0, n_events: 0 }] };
  expect(reportDay(history, "2026-09-19")).toBe("2026-09-17");
  expect(reportDay({ ...history, points: [] }, "2026-09-19")).toBe("2026-09-19");
  expect(reportDay(null, "2026-09-19")).toBe("2026-09-19");
});

test("reportParts splits the summary, the sections and the model footer", () => {
  const markdown = [
    "# EURUSD 2026-09-19: -21 lean against",
    "",
    "The macro backdrop scores -21 today, in the lean-against band.",
    "",
    "## Components",
    "",
    "- N: -0.70",
    "",
    "---",
    "",
    "Summary by claude_code/opus.",
    "",
  ].join("\n");
  const parts = reportParts(markdown);
  expect(parts.title).toBe("EURUSD 2026-09-19: -21 lean against");
  expect(parts.summary).toBe("The macro backdrop scores -21 today, in the lean-against band.");
  expect(parts.model).toBe("claude_code/opus");
  expect(parts.rest.startsWith("## Components")).toBe(true);
  expect(parts.rest.includes("Summary by")).toBe(false);
  const template = reportParts("# EURUSD 2026-09-18: -23 lean against\n\n## Components\n\n- N: -0.71\n");
  expect(template.summary).toBe("");
  expect(template.model).toBe("");
  expect(reportParts("")).toEqual({ title: "", summary: "", model: "", rest: "" });
});

test("the TradingView embed follows the symbol and the theme, a bare daily chart", () => {
  const url = new URL(tradingViewUrl("BITSTAMP:BTCUSD", "dark")!);
  expect(url.origin).toBe("https://s.tradingview.com");
  expect(url.pathname).toBe("/widgetembed/");
  expect(url.searchParams.get("symbol")).toBe("BITSTAMP:BTCUSD");
  expect(url.searchParams.get("interval")).toBe("D");
  expect(url.searchParams.get("theme")).toBe("dark");
  expect(url.searchParams.get("hide_top_toolbar")).toBe("1");
  expect(tradingViewUrl(null, "light")).toBeNull();
});

test("the theme name is the explicit choice, else the system preference", () => {
  expect(themeName("dark", false)).toBe("dark");
  expect(themeName("light", true)).toBe("light");
  expect(themeName(undefined, true)).toBe("dark");
  expect(themeName(undefined, false)).toBe("light");
});
