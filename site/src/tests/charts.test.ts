import { expect, test } from "vitest";

import type { AssetHistory, AssetSummary, CalendarEvent, ChainSeries } from "../api/types";
import {
  COMPONENT_COLORS,
  type Tokens,
  bandColor,
  chainFigures,
  componentsFigure,
  layoutTemplate,
  scoreFigure,
  sparkline,
} from "../lib/charts";

export const TOKENS: Tokens = {
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
    lean_for: "#7fc48a",
    tailwind: "#1f8a3b",
  },
  bandFillAlpha: 0.12,
};

const HISTORY: AssetHistory = {
  symbol: "EURUSD",
  formula: "v1",
  scale: { low: 0, high: 100, neutral: 50, edges: [30, 45, 55, 70] },
  points: [
    { date: "2026-09-16", score: 41.2, band: "lean_against", components: { N: -0.5, S: -0.1, R: 1 }, n_news: 80, n_events: 100 },
    { date: "2026-09-17", score: 40.8, band: "lean_against", components: { N: -0.55, S: -0.09, R: 1 }, n_news: 85, n_events: 116 },
  ],
};

function event(overrides: Partial<CalendarEvent>): CalendarEvent {
  return {
    id: "x",
    date: "2026-09-17T12:30:00Z",
    country: "united_states",
    event: "CPI",
    category: "inflation",
    importance: 3,
    consensus: null,
    previous: null,
    actual: null,
    ...overrides,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const any = (value: unknown) => value as any;

test("the layout template carries the tokens and hides the chrome", () => {
  const layout = any(layoutTemplate(TOKENS));
  expect(layout.paper_bgcolor).toBe(TOKENS.surface);
  expect(layout.font.color).toBe(TOKENS.ink);
  expect(layout.xaxis.gridcolor).toBe(TOKENS.grid);
  expect(layout.showlegend).toBe(false);
  expect(any(layoutTemplate({ ...TOKENS, surface: "#1a1a19" })).paper_bgcolor).toBe("#1a1a19");
});

test("bandColor maps each band to its token, unknown to muted", () => {
  expect(bandColor("tailwind", TOKENS)).toBe("#1f8a3b");
  expect(bandColor("whatever", TOKENS)).toBe(TOKENS.muted);
});

test("the sparkline is one muted line plus the emphasised last point, no chrome", () => {
  const summary = { band: "lean_against", sparkline: [40, 42, 41.5, 45] } as AssetSummary;
  const { data, layout, config } = sparkline(summary, TOKENS);
  const [line, last] = data.map(any);
  expect(line.y).toEqual([40, 42, 41.5, 45]);
  expect(line.x).toEqual([0, 1, 2, 3]);
  expect(line.line.color).toBe(TOKENS.muted);
  expect(line.hoverinfo).toBe("skip");
  expect(last.x).toEqual([3]);
  expect(last.marker.color).toBe(TOKENS.bands.lean_against);
  expect(any(layout).xaxis.visible).toBe(false);
  expect(layout.height).toBe(48);
  expect(config.displayModeBar).toBe(false);
  expect(any(sparkline({ band: "neutral", sparkline: [50] } as AssetSummary, TOKENS).data[1]).x).toEqual([0]);
});

test("the score figure: area over the dates, band shading, the neutral line, event hairlines", () => {
  const events = [event({ id: "cpi" }), event({ id: "ecb", date: "2026-09-17T11:45:00Z", event: "ECB Rate Decision", country: "euro_area" })];
  const { data, layout } = scoreFigure(HISTORY, events, TOKENS);
  const [area, marks] = data.map(any);
  expect(area.x).toEqual(["2026-09-16", "2026-09-17"]);
  expect(area.y).toEqual([41.2, 40.8]);
  expect(area.fill).toBe("tozeroy");
  expect(area.text[1]).toMatch(/N -0\.55/);
  expect(any(layout).yaxis.range).toEqual([0, 100]);
  expect(any(layout).yaxis.tickvals).toEqual([0, 30, 45, 55, 70, 100]);
  const shapes = any(layout.shapes) as { name: string; y0: number; y1: number; x0: unknown; fillcolor?: string }[];
  const bands = shapes.filter((shape) => shape.name === "band");
  expect(bands.map((shape) => [shape.y0, shape.y1])).toEqual([[0, 30], [30, 45], [45, 55], [55, 70], [70, 100]]);
  expect(bands[0]?.fillcolor).toBe("rgba(227,73,72,0.12)");
  expect(shapes.find((shape) => shape.name === "neutral")?.y0).toBe(50);
  const hairlines = shapes.filter((shape) => shape.name === "event");
  expect(hairlines.length).toBe(1); // two events on the same day, one hairline
  expect(marks.text[0]).toBe("CPI · ECB Rate Decision");
});

test("the score figure follows a -100..100 scale", () => {
  const history: AssetHistory = { ...HISTORY, formula: "v2", scale: { low: -100, high: 100, neutral: 0, edges: [-40, -10, 10, 40] } };
  const { data, layout } = scoreFigure(history, [], TOKENS);
  expect(any(layout).yaxis.range).toEqual([-100, 100]);
  expect(any(layout).yaxis.tickvals).toEqual([-100, -40, -10, 10, 40, 100]);
  expect(any(layout.shapes).find((shape: { name: string }) => shape.name === "neutral").y0).toBe(0);
  expect(any(data[1]).y).toEqual([]);
});

test("the components figure: one trace per component in fixed order, its own scale", () => {
  const { data, layout } = componentsFigure(HISTORY, TOKENS);
  expect(data.map((trace) => any(trace).name)).toEqual(["N", "S", "R"]);
  expect(any(data[0]).y).toEqual([-0.5, -0.55]);
  expect(data.map((trace) => any(trace).line.color)).toEqual(["N", "S", "R"].map((name) => COMPONENT_COLORS[name]));
  expect(any(layout).yaxis.range).toEqual([-1.05, 1.05]);
  expect(any(layout.annotations)[0].text).toBe("N");
  const empty = componentsFigure({ ...HISTORY, points: [] }, TOKENS);
  expect(empty.data).toEqual([]);
  expect(empty.layout.annotations).toEqual([]);
});

test("one small figure per on-chain series, labelled, thin line, values formatted compact", () => {
  const series: ChainSeries[] = [
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
  const [addresses, mvrv] = chainFigures(series, TOKENS);
  expect(addresses?.label).toBe("Active addresses");
  expect(addresses?.latest).toBe("587k");
  expect(any(addresses?.data[0]).y).toEqual([681346, 586590]);
  expect(any(addresses?.data[0]).line.width).toBe(2);
  expect(addresses?.layout.paper_bgcolor).toBe(TOKENS.surface);
  expect(mvrv?.latest).toBe("1.52");
  expect(chainFigures([], TOKENS)).toEqual([]);
});
