// Plotly figures built from the CSS tokens, so charts and UI share one palette.
// Everything here is a pure function of (data, tokens); the pages call Plotly.react.

import { BANDS } from "./format.js";

const TOKEN_VARS = {
  surface: "--surface",
  ink: "--ink",
  ink2: "--ink-2",
  muted: "--muted",
  grid: "--grid",
  axis: "--axis",
  accent: "--accent",
  font: "--font",
};

export function readTokens(element = globalThis.document?.documentElement) {
  const style = getComputedStyle(element);
  const read = (name) => style.getPropertyValue(name).trim();
  const tokens = Object.fromEntries(
    Object.entries(TOKEN_VARS).map(([name, variable]) => [name, read(variable)]),
  );
  tokens.bands = Object.fromEntries(BANDS.map((band) => [band, read(`--band-${band}`)]));
  tokens.bandFillAlpha = Number(read("--band-fill-alpha")) || 0.12;
  return tokens;
}

export function bandColor(band, tokens) {
  return tokens.bands[band] ?? tokens.muted;
}

export function layoutTemplate(tokens) {
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

export const CHART_CONFIG = { displayModeBar: false, responsive: true, displaylogo: false };

export function sparkline(summary, tokens) {
  const points = summary.sparkline;
  const last = points.length - 1;
  const data = [
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
      y: [points[last]],
      marker: { color: bandColor(summary.band, tokens), size: 8 },
      hoverinfo: "skip",
    },
  ];
  const layout = {
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
