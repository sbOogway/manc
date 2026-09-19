import { test } from "node:test";
import assert from "node:assert/strict";

import {
  BANDS,
  bandLabel,
  bandOf,
  formatDate,
  formatDelta,
  formatNumber,
  formatPercent,
  formatScore,
  importanceLabel,
} from "../format.js";

test("the five bands in order, each with a label", () => {
  assert.deepEqual(BANDS, ["headwind", "lean_against", "neutral", "lean_for", "tailwind"]);
  assert.equal(bandLabel("lean_against"), "lean against");
  assert.equal(bandLabel("tailwind"), "tailwind");
  assert.equal(bandLabel("unknown"), "unknown");
});

test("bandOf follows the section 5 scale with inclusive floors", () => {
  assert.equal(bandOf(0), "headwind");
  assert.equal(bandOf(29.9), "headwind");
  assert.equal(bandOf(30), "lean_against");
  assert.equal(bandOf(45), "neutral");
  assert.equal(bandOf(55), "lean_for");
  assert.equal(bandOf(70), "tailwind");
  assert.equal(bandOf(100), "tailwind");
});

test("scores round to a whole number", () => {
  assert.equal(formatScore(49.25), "49");
  assert.equal(formatScore(62.5), "63");
  assert.equal(formatScore(null), "—");
});

test("deltas carry a sign and one decimal, null is a dash", () => {
  assert.equal(formatDelta(5), "+5.0");
  assert.equal(formatDelta(-0.42), "-0.4");
  assert.equal(formatDelta(0), "0.0");
  assert.equal(formatDelta(null), "—");
});

test("percent from a ratio, signed, one decimal", () => {
  assert.equal(formatPercent(0.2), "+20.0%");
  assert.equal(formatPercent(-0.0345), "-3.5%");
  assert.equal(formatPercent(null), "—");
});

test("numbers keep up to four significant decimals and group thousands", () => {
  assert.equal(formatNumber(1.1479), "1.1479");
  assert.equal(formatNumber(3650), "3,650");
  assert.equal(formatNumber(-167000000000), "-167,000,000,000");
  assert.equal(formatNumber(3), "3");
  assert.equal(formatNumber(null), "—");
});

test("dates render short and ISO input stays ISO for keys", () => {
  assert.equal(formatDate("2026-09-19"), "19 Sep 2026");
  assert.equal(formatDate("2026-09-19T12:30:00Z"), "19 Sep 2026");
  assert.equal(formatDate(null), "—");
});

test("importance labels", () => {
  assert.equal(importanceLabel(3), "high");
  assert.equal(importanceLabel(2), "medium");
  assert.equal(importanceLabel(1), "low");
  assert.equal(importanceLabel(7), "7");
});
