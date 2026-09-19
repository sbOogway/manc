import { test } from "node:test";
import assert from "node:assert/strict";

import { eventRiskLabel, tileModel } from "../pages/overview.js";

test("event risk reads as a word", () => {
  assert.equal(eventRiskLabel(0), "quiet");
  assert.equal(eventRiskLabel(0.24), "quiet");
  assert.equal(eventRiskLabel(0.25), "busy week");
  assert.equal(eventRiskLabel(0.5), "busy week");
  assert.equal(eventRiskLabel(0.75), "heavy week");
  assert.equal(eventRiskLabel(1), "heavy week");
});

test("the tile shows the formatted score, band, delta and date", () => {
  const model = tileModel({
    symbol: "EURUSD",
    kind: "forex",
    formula: "v1",
    date: "2026-09-18",
    score: 40.78,
    band: "lean_against",
    delta: -0.42,
    sparkline: [41.2, 40.78],
    event_risk: 1,
  });
  assert.equal(model.score, "41");
  assert.equal(model.bandLabel, "lean against");
  assert.equal(model.delta, "-0.4");
  assert.equal(model.deltaClass, "down");
  assert.equal(model.date, "18 Sep 2026");
  assert.equal(model.risk, "heavy week");
  assert.equal(model.kind, "forex");
});

test("a first-day tile has no delta and a flat class", () => {
  const model = tileModel({ score: 55, band: "lean_for", delta: null, event_risk: 0, date: "2026-09-18" });
  assert.equal(model.delta, "—");
  assert.equal(model.deltaClass, "flat");
  assert.equal(tileModel({ score: 50, band: "neutral", delta: 0, event_risk: 0 }).deltaClass, "flat");
  assert.equal(tileModel({ score: 50, band: "neutral", delta: 2, event_risk: 0 }).deltaClass, "up");
});
