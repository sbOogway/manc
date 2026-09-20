import { expect, test } from "vitest";

import type { AssetSummary } from "../api/types";
import { eventRiskLabel, filterByKind, kindLabel, kindsOf, tileModel } from "../lib/overview";

function summary(overrides: Partial<AssetSummary>): AssetSummary {
  return {
    symbol: "EURUSD",
    kind: "forex",
    formula: "v2",
    date: "2026-09-18",
    score: 0,
    band: "neutral",
    delta: null,
    sparkline: [0],
    event_risk: 0,
    ...overrides,
  };
}

test("event risk reads as a word", () => {
  expect(eventRiskLabel(0)).toBe("quiet");
  expect(eventRiskLabel(0.24)).toBe("quiet");
  expect(eventRiskLabel(0.25)).toBe("busy week");
  expect(eventRiskLabel(0.75)).toBe("heavy week");
});

test("the tile shows the formatted score, band, delta and date", () => {
  const model = tileModel(summary({ score: 40.78, band: "lean_against", delta: -0.42, event_risk: 1 }));
  expect(model.score).toBe("41");
  expect(model.bandLabel).toBe("lean against");
  expect(model.delta).toBe("-0.4");
  expect(model.deltaClass).toBe("down");
  expect(model.date).toBe("18 Sep 2026");
  expect(model.risk).toBe("heavy week");
});

test("a first-day tile has no delta and a flat class", () => {
  expect(tileModel(summary({ delta: null })).delta).toBe("—");
  expect(tileModel(summary({ delta: null })).deltaClass).toBe("flat");
  expect(tileModel(summary({ delta: 0 })).deltaClass).toBe("flat");
  expect(tileModel(summary({ delta: 2 })).deltaClass).toBe("up");
});

test("kindsOf is distinct, in a fixed order, and filterByKind keeps the API order", () => {
  const summaries = [
    summary({ symbol: "SPX", kind: "equity_index" }),
    summary({ symbol: "EURUSD", kind: "forex" }),
    summary({ symbol: "BTCUSD", kind: "crypto" }),
    summary({ symbol: "GBPUSD", kind: "forex" }),
    summary({ symbol: "US10Y", kind: "bond" }),
  ];
  expect(kindsOf(summaries)).toEqual(["forex", "equity_index", "crypto", "bond"]);
  expect(filterByKind(summaries, "forex").map((row) => row.symbol)).toEqual(["EURUSD", "GBPUSD"]);
  expect(filterByKind(summaries, "all")).toEqual(summaries);
  expect(filterByKind(summaries, "metal")).toEqual([]);
});

test("kind labels read as words", () => {
  expect(kindLabel("equity_index")).toBe("equity indices");
  expect(kindLabel("bond")).toBe("bonds");
  expect(kindLabel("all")).toBe("all");
});
