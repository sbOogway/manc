import { test } from "node:test";
import assert from "node:assert/strict";

import { economiesOf, eventTime, groupByDay } from "../pages/events.js";

const EVENTS = [
  { id: "a", date: "2026-09-22T12:30:00Z", country: "united_states", event: "CPI", importance: 3 },
  { id: "b", date: "2026-09-22T14:00:00Z", country: "euro_area", event: "Speech", importance: 1 },
  { id: "c", date: "2026-09-23T08:00:00Z", country: "united_kingdom", event: "GDP", importance: 2 },
];

test("groupByDay keeps one group per day and the row order", () => {
  const groups = groupByDay(EVENTS);
  assert.deepEqual(groups.map((group) => group.day), ["2026-09-22", "2026-09-23"]);
  assert.deepEqual(groups[0].events.map((event) => event.id), ["a", "b"]);
  assert.deepEqual(groupByDay([]), []);
});

test("economiesOf is distinct and sorted", () => {
  assert.deepEqual(economiesOf([...EVENTS, EVENTS[0]]), ["euro_area", "united_kingdom", "united_states"]);
});

test("eventTime is HH:MM UTC", () => {
  assert.equal(eventTime("2026-09-22T12:30:00Z"), "12:30");
  assert.equal(eventTime("2026-09-22T08:05:00+00:00"), "08:05");
});
