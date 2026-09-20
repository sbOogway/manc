import { expect, test } from "vitest";

import type { CalendarEvent } from "../api/types";
import { calendarEntries, economiesOf, eventDetails, eventTime, filterEvents } from "../lib/events";

function event(overrides: Partial<CalendarEvent>): CalendarEvent {
  return { id: "x", date: "2026-09-22T12:30:00Z", country: "united_states", event: "CPI", category: "inflation", importance: 3, consensus: 3.1, previous: 2.9, actual: null, ...overrides };
}

test("economiesOf is distinct and sorted", () => {
  const events = [event({ country: "united_states" }), event({ country: "euro_area" }), event({ country: "united_states" })];
  expect(economiesOf(events)).toEqual(["euro_area", "united_states"]);
});

test("eventTime is HH:MM UTC", () => {
  expect(eventTime("2026-09-22T12:30:00Z")).toBe("12:30");
});

test("filterEvents by importance floor and economy", () => {
  const events = [event({ id: "a", importance: 3 }), event({ id: "b", importance: 1 }), event({ id: "c", country: "japan", importance: 2 })];
  expect(filterEvents(events, 2, null).map((one) => one.id)).toEqual(["a", "c"]);
  expect(filterEvents(events, 1, "japan").map((one) => one.id)).toEqual(["c"]);
});

test("calendarEntries carry the time, the importance class and the details", () => {
  const [entry] = calendarEntries([event({ id: "cpi" })]);
  expect(entry?.id).toBe("cpi");
  expect(entry?.title).toBe("CPI");
  expect(entry?.start).toBe("2026-09-22T12:30:00Z");
  expect(entry?.classNames).toEqual(["importance-3"]);
  expect(entry?.extendedProps.country).toBe("united states");
  expect(eventDetails(event({}))).toBe("12:30 UTC · united states · high\nconsensus 3.1\nprevious 2.9");
  expect(eventDetails(event({ consensus: null, previous: null, importance: 1 }))).toBe("12:30 UTC · united states · low");
});
