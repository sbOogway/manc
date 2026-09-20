// Plotly figures built from the CSS tokens, so charts and UI share one palette.
// Everything here is a pure function of (data, tokens); PlotlyChart.vue calls Plotly.react.
import type { Config, Data, Layout } from "plotly.js";

import type { AssetHistory, AssetSummary, CalendarEvent, ChainSeries } from "../api/types";
import { BANDS, formatCompact } from "./format";

export interface Tokens {
  surface: string;
  ink: string;
  ink2: string;
  muted: string;
  grid: string;
  axis: string;
  accent: string;
  font: string;
  bands: Record<string, string>;
  bandFillAlpha: number;
}

export interface Figure {
  data: Partial<Data>[];
  layout: Partial<Layout>;
  config: Partial<Config>;
}

const TOKEN_VARS = {
  surface: "--surface",
  ink: "--ink",
  ink2: "--ink-2",
  muted: "--muted",
  grid: "--grid",
  axis: "--axis",
  accent: "--accent",
  font: "--font",
} as const;

export const CHART_CONFIG: Partial<Config> = { displayModeBar: false, responsive: true, displaylogo: false };
export const COMPONENT_COLORS: Record<string, string> = { N: "#eb6834", S: "#1baf7a", R: "#eda100", D: "#e87ba4" }; // categorical slots 2-5
const COMPONENT_NAMES: Record<string, string> = { N: "news", S: "surprise", R: "event risk", D: "dispersion" };

export function readTokens(element: Element = document.documentElement): Tokens {
  const style = getComputedStyle(element);
  const read = (name: string) => style.getPropertyValue(name).trim();
  return {
    surface: read(TOKEN_VARS.surface),
    ink: read(TOKEN_VARS.ink),
    ink2: read(TOKEN_VARS.ink2),
    muted: read(TOKEN_VARS.muted),
    grid: read(TOKEN_VARS.grid),
    axis: read(TOKEN_VARS.axis),
    accent: read(TOKEN_VARS.accent),
    font: read(TOKEN_VARS.font),
    bands: Object.fromEntries(BANDS.map((band) => [band, read(`--band-${band}`)])),
    bandFillAlpha: Number(read("--band-fill-alpha")) || 0.12,
  };
}

export function bandColor(band: string, tokens: Tokens): string {
  return tokens.bands[band] ?? tokens.muted;
}

export function layoutTemplate(tokens: Tokens): Partial<Layout> {
  const axis = {
    gridcolor: tokens.grid,
    linecolor: tokens.axis,
    zerolinecolor: tokens.axis,
    tickcolor: tokens.axis,
    tickfont: { color: tokens.muted },
  };
  return {
    paper_bgcolor: tokens.surface,
    plot_bgcolor: tokens.surface,
    font: { family: tokens.font, color: tokens.ink, size: 12 },
    xaxis: { ...axis },
    yaxis: { ...axis },
    hoverlabel: { bgcolor: tokens.surface, bordercolor: tokens.axis, font: { color: tokens.ink } },
    margin: { l: 40, r: 16, t: 16, b: 32 },
    showlegend: false,
  };
}

function rgba(hex: string, alpha: number): string {
  const [red, green, blue] = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16));
  return `rgba(${red},${green},${blue},${alpha})`;
}

export function sparkline(summary: AssetSummary, tokens: Tokens): Figure {
  const points = summary.sparkline;
  const last = points.length - 1;
  const data: Partial<Data>[] = [
    {
      type: "scatter",
      mode: "lines",
      x: points.map((_value, index) => index),
      y: points,
      line: { color: tokens.muted, width: 2, shape: "spline", smoothing: 0.6 },
      hoverinfo: "skip",
    },
    {
      type: "scatter",
      mode: "markers",
      x: [last],
      y: [points[last] ?? 0],
      marker: { color: bandColor(summary.band, tokens), size: 8 },
      hoverinfo: "skip",
    },
  ];
  const layout: Partial<Layout> = {
    ...layoutTemplate(tokens),
    height: 48,
    margin: { l: 0, r: 0, t: 0, b: 0 },
    xaxis: { visible: false, range: [-0.5, Math.max(last, 0) + 0.5] },
    yaxis: { visible: false },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
  };
  return { data, layout, config: CHART_CONFIG };
}

function componentText(components: Record<string, number>): string {
  return Object.entries(components)
    .map(([name, value]) => `${name} ${value.toFixed(2)}`)
    .join(" · ");
}

export function scoreFigure(history: AssetHistory, events: CalendarEvent[], tokens: Tokens): Figure {
  const points = history.points;
  const scale = history.scale;
  const floors = [scale.low, ...scale.edges, scale.high];
  const dates = points.map((point) => point.date);
  const byDay = new Map<string, string[]>();
  for (const event of events) {
    const day = event.date.slice(0, 10);
    byDay.set(day, [...(byDay.get(day) ?? []), event.event]);
  }
  const eventDays = [...byDay.keys()].sort();
  const data: Partial<Data>[] = [
    {
      type: "scatter",
      mode: "lines",
      name: "score",
      x: dates,
      y: points.map((point) => point.score),
      text: points.map((point) => componentText(point.components)),
      hovertemplate: "%{x}<br><b>%{y:.1f}</b><br>%{text}<extra></extra>",
      fill: "tozeroy",
      fillcolor: rgba(tokens.accent, 0.08),
      line: { color: tokens.accent, width: 2 },
    },
    {
      type: "scatter",
      mode: "markers",
      name: "events",
      x: eventDays,
      y: eventDays.map(() => scale.low + 0.02 * (scale.high - scale.low)),
      text: eventDays.map((day) => (byDay.get(day) ?? []).join(" · ")),
      hovertemplate: "%{x}<br>%{text}<extra></extra>",
      marker: { color: tokens.muted, size: 8, symbol: "diamond" },
    },
  ];
  const shapes: Partial<Layout>["shapes"] = BANDS.map((band, index) => ({
    name: "band",
    type: "rect",
    xref: "paper",
    x0: 0,
    x1: 1,
    y0: floors[index],
    y1: floors[index + 1],
    fillcolor: rgba(bandColor(band, tokens), tokens.bandFillAlpha),
    line: { width: 0 },
    layer: "below",
  }));
  shapes.push({
    name: "neutral",
    type: "line",
    xref: "paper",
    x0: 0,
    x1: 1,
    y0: scale.neutral,
    y1: scale.neutral,
    line: { color: tokens.axis, width: 1, dash: "dot" },
    layer: "below",
  });
  for (const day of eventDays) {
    shapes.push({
      name: "event",
      type: "line",
      x0: day,
      x1: day,
      yref: "paper",
      y0: 0,
      y1: 1,
      line: { color: tokens.axis, width: 1 },
      layer: "below",
    });
  }
  const template = layoutTemplate(tokens);
  const layout: Partial<Layout> = {
    ...template,
    height: 320,
    hovermode: "x unified",
    yaxis: { ...template.yaxis, range: [scale.low, scale.high], tickvals: floors, showgrid: false },
    xaxis: { ...template.xaxis, showgrid: false },
    shapes,
  };
  return { data, layout, config: CHART_CONFIG };
}

export function componentsFigure(history: AssetHistory, tokens: Tokens): Figure {
  const points = history.points;
  const names = points.length ? Object.keys(points[0]?.components ?? {}) : [];
  const data: Partial<Data>[] = names.map((name) => ({
    type: "scatter",
    mode: "lines",
    name,
    x: points.map((point) => point.date),
    y: points.map((point) => point.components[name] ?? 0),
    line: { color: COMPONENT_COLORS[name] ?? tokens.muted, width: 2 },
    hovertemplate: `${COMPONENT_NAMES[name] ?? name} %{y:.2f}<extra></extra>`,
  }));
  const last = points.at(-1);
  const annotations: Partial<Layout>["annotations"] = last
    ? names.map((name) => ({
        text: name,
        x: last.date,
        y: last.components[name] ?? 0,
        xanchor: "left",
        showarrow: false,
        font: { color: COMPONENT_COLORS[name] ?? tokens.muted, size: 11 },
      }))
    : [];
  const template = layoutTemplate(tokens);
  const layout: Partial<Layout> = {
    ...template,
    height: 160,
    hovermode: "x unified",
    margin: { ...template.margin, r: 24, t: 4 },
    yaxis: { ...template.yaxis, range: [-1.05, 1.05], tickvals: [-1, 0, 1], zeroline: true },
    xaxis: { ...template.xaxis, showgrid: false },
    annotations,
  };
  return { data, layout, config: CHART_CONFIG };
}

export interface ChainFigure extends Figure {
  metric: string;
  label: string;
  source: string;
  latest: string;
}

export function chainFigures(series: ChainSeries[], tokens: Tokens): ChainFigure[] {
  // Small multiples: one thin line per on-chain series, the latest value as the headline.
  const template = layoutTemplate(tokens);
  return series.map((one) => ({
    metric: one.metric,
    label: one.label,
    source: one.source,
    latest: formatCompact(one.points.at(-1)?.value),
    data: [
      {
        type: "scatter",
        mode: "lines",
        x: one.points.map((point) => point.date),
        y: one.points.map((point) => point.value),
        line: { color: tokens.accent, width: 2 },
        hovertemplate: "%{x}<br><b>%{y:,.4~s}</b><extra></extra>",
      },
    ],
    layout: {
      ...template,
      height: 140,
      margin: { l: 48, r: 8, t: 4, b: 24 },
      xaxis: { ...template.xaxis, showgrid: false },
      yaxis: { ...template.yaxis, tickformat: "~s", nticks: 3 },
    },
    config: CHART_CONFIG,
  }));
}
