import { test } from "node:test";
import assert from "node:assert/strict";

import {
  chainFigures,
  themeName,
  tradingViewUrl,
  COMPONENT_COLORS,
  componentsFigure,
  eventsFor,
  forecastRows,
  headlineRows,
  rangeFor,
  reportDay,
  reportParts,
  revision,
  scoreFigure,
} from "../pages/asset.js";

const TOKENS = {
  surface: "#fcfcfb",
  ink: "#0b0b0b",
  ink2: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  accent: "#2a78d6",
  font: "system-ui",
  bands: {
    headwind: "#e34948",
    lean_against: "#ef8c8b",
    neutral: "#898781",
    lean_for: "#86b6ef",
    tailwind: "#2a78d6",
  },
  bandFillAlpha: 0.12,
};

const HISTORY = {
  symbol: "EURUSD",
  formula: "v1",
  scale: { low: 0, high: 100, neutral: 50, edges: [30, 45, 55, 70] },
  points: [
    { date: "2026-09-16", score: 41.2, band: "lean_against", components: { N: -0.5, S: -0.1, R: 1 }, n_news: 80, n_events: 100 },
    { date: "2026-09-17", score: 40.8, band: "lean_against", components: { N: -0.55, S: -0.09, R: 1 }, n_news: 85, n_events: 116 },
  ],
};

test("rangeFor gives ISO from/to for every preset", () => {
  const today = "2026-09-19";
  assert.deepEqual(rangeFor(30, today), { from: "2026-08-20", to: "2026-09-19" });
  assert.deepEqual(rangeFor(90, today), { from: "2026-06-21", to: "2026-09-19" });
  assert.deepEqual(rangeFor(365, today), { from: "2025-09-19", to: "2026-09-19" });
});

test("the score figure: area over the dates, band shading, the 50 line, event hairlines", () => {
  const events = [
    { id: "cpi", date: "2026-09-17T12:30:00Z", event: "CPI", country: "united_states", importance: 3 },
    { id: "ecb", date: "2026-09-17T11:45:00Z", event: "ECB Rate Decision", country: "euro_area", importance: 3 },
  ];
  const { data, layout } = scoreFigure(HISTORY, events, TOKENS);
  const [area] = data;
  assert.deepEqual(area.x, ["2026-09-16", "2026-09-17"]);
  assert.deepEqual(area.y, [41.2, 40.8]);
  assert.equal(area.fill, "tozeroy");
  assert.equal(area.line.color, TOKENS.accent);
  assert.equal(area.line.width, 2);
  assert.match(area.text[1], /N -0\.55/);
  assert.match(area.text[1], /S -0\.09/);
  assert.match(area.text[1], /R 1\.00/);
  assert.deepEqual(layout.yaxis.range, [0, 100]);
  assert.deepEqual(layout.yaxis.tickvals, [0, 30, 45, 55, 70, 100]);
  const bands = layout.shapes.filter((shape) => shape.name === "band");
  assert.equal(bands.length, 5);
  assert.deepEqual(bands.map((shape) => [shape.y0, shape.y1]), [[0, 30], [30, 45], [45, 55], [55, 70], [70, 100]]);
  assert.equal(bands[0].fillcolor, "rgba(227,73,72,0.12)");
  const neutral = layout.shapes.find((shape) => shape.name === "neutral");
  assert.deepEqual([neutral.y0, neutral.y1], [50, 50]);
  const hairlines = layout.shapes.filter((shape) => shape.name === "event");
  assert.equal(hairlines.length, 1); // two events on the same day, one hairline
  assert.equal(hairlines[0].x0, "2026-09-17");
  const [, marks] = data;
  assert.deepEqual(marks.x, ["2026-09-17"]);
  assert.equal(marks.text[0], "CPI · ECB Rate Decision");
  assert.equal(layout.showlegend, false);
});

test("the score figure follows a -100..100 scale", () => {
  const history = { ...HISTORY, formula: "v2", scale: { low: -100, high: 100, neutral: 0, edges: [-40, -10, 10, 40] } };
  const { data, layout } = scoreFigure(history, [], TOKENS);
  assert.deepEqual(layout.yaxis.range, [-100, 100]);
  assert.deepEqual(layout.yaxis.tickvals, [-100, -40, -10, 10, 40, 100]);
  const bands = layout.shapes.filter((shape) => shape.name === "band");
  assert.deepEqual(bands.map((shape) => [shape.y0, shape.y1]), [[-100, -40], [-40, -10], [-10, 10], [10, 40], [40, 100]]);
  const neutral = layout.shapes.find((shape) => shape.name === "neutral");
  assert.equal(neutral.y0, 0);
  assert.equal(data[0].fill, "tozeroy"); // the area fills toward 0, the neutral point
  assert.equal(data[1].y[0], undefined); // no event marks without events
});

test("the components figure: one trace per component in fixed order, its own scale", () => {
  const { data, layout } = componentsFigure(HISTORY, TOKENS);
  assert.deepEqual(data.map((trace) => trace.name), ["N", "S", "R"]);
  assert.deepEqual(componentsFigure({ ...HISTORY, points: HISTORY.points.map((point) => ({ ...point, components: { ...point.components, D: 0.3 } })) }, TOKENS).data.map((trace) => trace.name), ["N", "S", "R", "D"]);
  assert.deepEqual(data[0].y, [-0.5, -0.55]);
  assert.deepEqual(data.map((trace) => trace.line.color), ["N", "S", "R"].map((name) => COMPONENT_COLORS[name]));
  assert.deepEqual(layout.yaxis.range, [-1.05, 1.05]);
  assert.equal(layout.annotations.length, 3);
  assert.equal(layout.annotations[0].text, "N");
  assert.equal(layout.annotations[0].y, -0.55);
});

test("the components figure on an empty history has no traces", () => {
  const { data, layout } = componentsFigure({ points: [] }, TOKENS);
  assert.deepEqual(data, []);
  assert.deepEqual(layout.annotations, []);
});

test("eventsFor keeps the asset's economies in the window, in order", () => {
  const events = [
    { id: "past", date: "2026-09-18T12:00:00Z", country: "united_states", importance: 3 },
    { id: "soon", date: "2026-09-20T12:00:00Z", country: "euro_area", importance: 2 },
    { id: "other", date: "2026-09-21T12:00:00Z", country: "japan", importance: 3 },
    { id: "later", date: "2026-09-30T12:00:00Z", country: "united_states", importance: 3 },
    { id: "far", date: "2026-10-10T12:00:00Z", country: "united_states", importance: 3 },
  ];
  const kept = eventsFor(events, ["euro_area", "united_states"], "2026-09-19", 14);
  assert.deepEqual(kept.map((event) => event.id), ["soon", "later"]);
});

test("forecastRows groups by horizon with the median last", () => {
  const panel = {
    rows: [
      { institution: "goldman_sachs", horizon_date: "2026-12-31", horizon_label: "year-end", value: 1.2, previous_value: 1.1, vs_spot: 0.05, published_at: "2026-09-17T10:00:00Z", confidence: 0.9 },
      { institution: "goldman_sachs", horizon_date: "2027-06-30", horizon_label: "12 months", value: 1.25, previous_value: null, vs_spot: 0.09, published_at: "2026-09-17T10:00:00Z", confidence: 0.9 },
      { institution: "ing", horizon_date: "2026-12-31", horizon_label: "year-end", value: 1.15, previous_value: 1.18, vs_spot: 0.0, published_at: "2026-09-18T10:00:00Z", confidence: 0.7 },
    ],
    medians: [
      { horizon_date: "2026-12-31", value: 1.175 },
      { horizon_date: "2027-06-30", value: 1.25 },
    ],
    spot: 1.1479,
  };
  const groups = forecastRows(panel);
  assert.deepEqual(groups.map((group) => group.horizon), ["2026-12-31", "2027-06-30"]);
  assert.deepEqual(groups[0].rows.map((row) => row.institution), ["goldman sachs", "ing"]);
  assert.equal(groups[0].median.value, 1.175);
  assert.equal(groups[0].median.vsSpot, "+2.4%");
  assert.equal(groups[0].rows[0].vsSpot, "+5.0%");
  assert.equal(groups[0].rows[0].revision, "▲");
  assert.equal(groups[0].rows[1].revision, "▼");
  assert.equal(groups[1].rows[0].revision, "—");
  assert.equal(groups[0].rows[0].published, "17 Sep 2026");
  assert.equal(groups[0].label, "year-end");
});

test("forecastRows without a spot leaves the median distance blank", () => {
  const groups = forecastRows({ rows: [{ institution: "ing", horizon_date: "2026-12-31", horizon_label: "ye", value: 1.1, previous_value: null, vs_spot: null, published_at: "2026-09-18T00:00:00Z", confidence: 0.6 }], medians: [{ horizon_date: "2026-12-31", value: 1.1 }], spot: null });
  assert.equal(groups[0].median.vsSpot, "—");
  assert.equal(groups[0].rows[0].vsSpot, "—");
});

test("revision arrows", () => {
  assert.equal(revision({ value: 1.2, previous_value: 1.1 }), "▲");
  assert.equal(revision({ value: 1.0, previous_value: 1.1 }), "▼");
  assert.equal(revision({ value: 1.1, previous_value: 1.1 }), "—");
  assert.equal(revision({ value: 1.1, previous_value: null }), "—");
});

test("headlineRows scales the weight bars to the strongest headline, in API order", () => {
  const rows = headlineRows([
    { title: "a", url: "u/a", source: "reuters", published_at: "2026-09-18T10:00:00Z", direction: -1, confidence: 0.8, source_weight: 1.0, weight: 0.8 },
    { title: "b", url: "u/b", source: "fxstreet", published_at: "2026-09-18T09:00:00Z", direction: 1, confidence: 0.9, source_weight: 0.6, weight: 0.54 },
    { title: "c", url: "u/c", source: "blog", published_at: "2026-09-17T09:00:00Z", direction: 1, confidence: 0.2, source_weight: 1.0, weight: 0.2 },
  ]);
  assert.deepEqual(rows.map((row) => row.title), ["a", "b", "c"]);
  assert.deepEqual(rows.map((row) => row.bar), [100, 67.5, 25]);
  assert.deepEqual(rows.map((row) => row.weight), ["0.80", "0.54", "0.20"]);
  assert.deepEqual(rows.map((row) => row.glyph), ["▼", "▲", "▲"]);
  assert.equal(rows[0].date, "18 Sep 2026");
  assert.deepEqual(headlineRows([]), []);
});

test("reportDay is the last scored day, or today without scores", () => {
  assert.equal(reportDay(HISTORY, "2026-09-19"), "2026-09-17");
  assert.equal(reportDay({ points: [] }, "2026-09-19"), "2026-09-19");
  assert.equal(reportDay(null, "2026-09-19"), "2026-09-19");
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
    "## Headlines",
    "",
    "- ▼ Euro slips (reuters, 2026-09-18, 0.90)",
    "",
    "---",
    "",
    "Summary by claude_code/opus.",
    "",
  ].join("\n");
  const parts = reportParts(markdown);
  assert.equal(parts.title, "EURUSD 2026-09-19: -21 lean against");
  assert.equal(parts.summary, "The macro backdrop scores -21 today, in the lean-against band.");
  assert.equal(parts.model, "claude_code/opus");
  assert.ok(parts.rest.startsWith("## Components"));
  assert.ok(parts.rest.includes("## Headlines"));
  assert.ok(!parts.rest.includes("Summary by"));
});

test("reportParts on a template-only report has no summary and no model", () => {
  const markdown = "# EURUSD 2026-09-18: -23 lean against\n\n## Components\n\n- N: -0.71\n";
  const parts = reportParts(markdown);
  assert.equal(parts.summary, "");
  assert.equal(parts.model, "");
  assert.ok(parts.rest.startsWith("## Components"));
  assert.deepEqual(reportParts(""), { title: "", summary: "", model: "", rest: "" });
});

test("the TradingView embed follows the symbol, the theme and shows a bare daily chart", () => {
  const url = new URL(tradingViewUrl("BITSTAMP:BTCUSD", "dark"));
  assert.equal(url.origin, "https://s.tradingview.com");
  assert.equal(url.pathname, "/widgetembed/");
  assert.equal(url.searchParams.get("symbol"), "BITSTAMP:BTCUSD");
  assert.equal(url.searchParams.get("interval"), "D");
  assert.equal(url.searchParams.get("theme"), "dark");
  assert.equal(url.searchParams.get("hide_top_toolbar"), "1");
  assert.equal(url.searchParams.get("symboledit"), "0");
  assert.equal(new URL(tradingViewUrl("FX:EURUSD", "light")).searchParams.get("theme"), "light");
  assert.equal(tradingViewUrl(null, "light"), null); // no ticker, no frame
});

test("the theme name is the explicit choice, else the system preference", () => {
  assert.equal(themeName("dark", false), "dark");
  assert.equal(themeName("light", true), "light");
  assert.equal(themeName(undefined, true), "dark");
  assert.equal(themeName(undefined, false), "light");
});

test("one small figure per on-chain series, labelled, thin line, values formatted compact", () => {
  const series = [
    {
      metric: "active_addresses",
      label: "Active addresses",
      source: "coinmetrics",
      points: [
        { date: "2026-09-18", value: 681346 },
        { date: "2026-09-19", value: 586590 },
      ],
    },
    { metric: "mvrv", label: "MVRV", source: "coinmetrics", points: [{ date: "2026-09-19", value: 1.52 }] },
  ];
  const figures = chainFigures(series, TOKENS);
  assert.equal(figures.length, 2);
  const [addresses, mvrv] = figures;
  assert.equal(addresses.metric, "active_addresses");
  assert.equal(addresses.label, "Active addresses");
  assert.equal(addresses.latest, "587k");
  assert.deepEqual(addresses.data[0].x, ["2026-09-18", "2026-09-19"]);
  assert.deepEqual(addresses.data[0].y, [681346, 586590]);
  assert.equal(addresses.data[0].line.width, 2);
  assert.equal(addresses.layout.paper_bgcolor, TOKENS.surface);
  assert.equal(addresses.layout.showlegend, false);
  assert.equal(mvrv.latest, "1.52");
  assert.deepEqual(chainFigures([], TOKENS), []);
});
