import { test } from "node:test";
import assert from "node:assert/strict";

import { calendarWeeks, economiesOf, eventTime } from "../pages/events.js";

const EVENTS = [
  { id: "a", date: "2026-09-22T12:30:00Z", country: "united_states", event: "CPI", importance: 3 },
  { id: "b", date: "2026-09-22T14:00:00Z", country: "euro_area", event: "Speech", importance: 1 },
  { id: "c", date: "2026-09-23T08:00:00Z", country: "united_kingdom", event: "GDP", importance: 2 },
];

test("economiesOf is distinct and sorted", () => {
  assert.deepEqual(economiesOf([...EVENTS, EVENTS[0]]), ["euro_area", "united_kingdom", "united_states"]);
});

test("eventTime is HH:MM UTC", () => {
  assert.equal(eventTime("2026-09-22T12:30:00Z"), "12:30");
  assert.equal(eventTime("2026-09-22T08:05:00+00:00"), "08:05");
});

test("calendarWeeks spans whole weeks around the window, events on their day in time order", () => {
  const events = [
    { id: "late", date: "2026-09-22T14:00:00Z", country: "euro_area", event: "Speech", importance: 1 },
    { id: "early", date: "2026-09-22T12:30:00Z", country: "united_states", event: "CPI", importance: 3 },
    { id: "last", date: "2026-10-19T08:00:00Z", country: "united_kingdom", event: "GDP", importance: 2 },
    { id: "out", date: "2026-10-20T08:00:00Z", country: "united_kingdom", event: "Out", importance: 2 },
  ];
  const weeks = calendarWeeks(events, "2026-09-19", 30); // a Saturday; window ends 2026-10-19, a Monday
  assert.equal(weeks[0][0].day, "2026-09-14"); // Monday of today's week
  assert.equal(weeks.at(-1)[6].day, "2026-10-25"); // Sunday of the last window week
  assert.equal(weeks.length, 6);
  assert.ok(weeks.every((week) => week.length === 7));
  const cells = weeks.flat();
  assert.deepEqual(cells.filter((cell) => cell.today).map((cell) => cell.day), ["2026-09-19"]);
  assert.equal(cells.find((cell) => cell.day === "2026-09-18").inWindow, false);
  assert.equal(cells.find((cell) => cell.day === "2026-09-19").inWindow, true);
  assert.equal(cells.find((cell) => cell.day === "2026-10-19").inWindow, true);
  assert.equal(cells.find((cell) => cell.day === "2026-10-20").inWindow, false);
  assert.deepEqual(cells.find((cell) => cell.day === "2026-09-22").events.map((event) => event.id), ["early", "late"]);
  assert.deepEqual(cells.find((cell) => cell.day === "2026-10-20").events, []); // outside the window, not shown
  assert.equal(cells.find((cell) => cell.day === "2026-09-14").dayOfMonth, 14);
  assert.equal(cells.find((cell) => cell.day === "2026-10-01").monthLabel, "Oct");
  assert.equal(cells.find((cell) => cell.day === "2026-10-02").monthLabel, "");
});
