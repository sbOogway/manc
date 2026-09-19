import { test } from "node:test";
import assert from "node:assert/strict";

import { bandColor, layoutTemplate, sparkline } from "../charts.js";

const TOKENS = {
  surface: "#fcfcfb",
  ink: "#0b0b0b",
  ink2: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  accent: "#2a78d6",
  font: "system-ui, sans-serif",
  bands: {
    headwind: "#e34948",
    lean_against: "#ef8c8b",
    neutral: "#898781",
    lean_for: "#86b6ef",
    tailwind: "#2a78d6",
  },
  bandFillAlpha: 0.12,
};

test("the layout template carries the tokens and hides the chrome", () => {
  const layout = layoutTemplate(TOKENS);
  assert.equal(layout.paper_bgcolor, TOKENS.surface);
  assert.equal(layout.plot_bgcolor, TOKENS.surface);
  assert.equal(layout.font.color, TOKENS.ink);
  assert.equal(layout.font.family, TOKENS.font);
  assert.equal(layout.xaxis.gridcolor, TOKENS.grid);
  assert.equal(layout.yaxis.gridcolor, TOKENS.grid);
  assert.equal(layout.xaxis.linecolor, TOKENS.axis);
  const dark = layoutTemplate({ ...TOKENS, surface: "#1a1a19", ink: "#ffffff" });
  assert.equal(dark.paper_bgcolor, "#1a1a19");
  assert.equal(dark.font.color, "#ffffff");
});

test("bandColor maps each band to its token, unknown to muted", () => {
  assert.equal(bandColor("tailwind", TOKENS), "#2a78d6");
  assert.equal(bandColor("lean_against", TOKENS), "#ef8c8b");
  assert.equal(bandColor("whatever", TOKENS), TOKENS.muted);
});

test("the sparkline is one muted line plus the emphasised last point, no chrome", () => {
  const summary = { symbol: "EURUSD", band: "lean_against", sparkline: [40, 42, 41.5, 45] };
  const { data, layout, config } = sparkline(summary, TOKENS);
  assert.equal(data.length, 2);
  const [line, last] = data;
  assert.deepEqual(line.y, [40, 42, 41.5, 45]);
  assert.deepEqual(line.x, [0, 1, 2, 3]);
  assert.equal(line.mode, "lines");
  assert.equal(line.line.color, TOKENS.muted);
  assert.equal(line.line.width, 2);
  assert.equal(line.hoverinfo, "skip");
  assert.deepEqual(last.x, [3]);
  assert.deepEqual(last.y, [45]);
  assert.equal(last.mode, "markers");
  assert.equal(last.marker.color, TOKENS.bands.lean_against);
  assert.ok(last.marker.size >= 8);
  assert.equal(layout.xaxis.visible, false);
  assert.equal(layout.yaxis.visible, false);
  assert.equal(layout.showlegend, false);
  assert.equal(layout.height, 48);
  assert.deepEqual(layout.margin, { l: 0, r: 0, t: 0, b: 0 });
  assert.equal(config.displayModeBar, false);
  assert.equal(config.responsive, true);
});

test("a one-point sparkline still renders", () => {
  const { data } = sparkline({ band: "neutral", sparkline: [50] }, TOKENS);
  assert.deepEqual(data[0].x, [0]);
  assert.deepEqual(data[1].x, [0]);
});
