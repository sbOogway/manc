import { expect, test } from "vitest";

import {
  BANDS,
  bandLabel,
  formatCompact,
  formatDate,
  formatDelta,
  formatNumber,
  formatPercent,
  formatScore,
  importanceLabel,
  shiftDays,
} from "../lib/format";

test("the five bands in order, each with a label", () => {
  expect(BANDS).toEqual(["headwind", "lean_against", "neutral", "lean_for", "tailwind"]);
  expect(bandLabel("lean_against")).toBe("lean against");
  expect(bandLabel("unknown")).toBe("unknown");
});

test("scores round to a whole number", () => {
  expect(formatScore(49.25)).toBe("49");
  expect(formatScore(62.5)).toBe("63");
  expect(formatScore(null)).toBe("—");
});

test("deltas carry a sign and one decimal, null is a dash", () => {
  expect(formatDelta(5)).toBe("+5.0");
  expect(formatDelta(-0.42)).toBe("-0.4");
  expect(formatDelta(0)).toBe("0.0");
  expect(formatDelta(null)).toBe("—");
});

test("percent from a ratio, signed, one decimal", () => {
  expect(formatPercent(0.2)).toBe("+20.0%");
  expect(formatPercent(-0.0345)).toBe("-3.5%");
  expect(formatPercent(null)).toBe("—");
});

test("numbers keep up to four decimals and group thousands", () => {
  expect(formatNumber(1.1479)).toBe("1.1479");
  expect(formatNumber(3650)).toBe("3,650");
  expect(formatNumber(-167000000000)).toBe("-167,000,000,000");
  expect(formatNumber(null)).toBe("—");
});

test("compact numbers for the on-chain tiles", () => {
  expect(formatCompact(586590)).toBe("587k");
  expect(formatCompact(15739176805.58)).toBe("15.74bn");
  expect(formatCompact(14277506)).toBe("14.3M");
  expect(formatCompact(1.5256)).toBe("1.53");
  expect(formatCompact(-120771340)).toBe("-120.8M");
  expect(formatCompact(null)).toBe("—");
});

test("dates render short and ISO input stays ISO for keys", () => {
  expect(formatDate("2026-09-19")).toBe("19 Sep 2026");
  expect(formatDate("2026-09-19T12:30:00Z")).toBe("19 Sep 2026");
  expect(formatDate(null)).toBe("—");
  expect(shiftDays("2026-09-30", 1)).toBe("2026-10-01");
});

test("importance labels", () => {
  expect(importanceLabel(3)).toBe("high");
  expect(importanceLabel(1)).toBe("low");
  expect(importanceLabel(7)).toBe("7");
});
