// The events page's pure helpers: filters and the FullCalendar event objects.
import type { CalendarEvent } from "../api/types";
import { formatNumber, importanceLabel, words } from "./format";

export const IMPORTANCE_CHOICES = [
  { label: "all", value: 1 },
  { label: "medium+", value: 2 },
  { label: "high", value: 3 },
] as const;

export function economiesOf(events: CalendarEvent[]): string[] {
  return [...new Set(events.map((event) => event.country))].sort();
}

export function eventTime(iso: string): string {
  return iso.slice(11, 16);
}

export function eventDetails(event: CalendarEvent): string {
  return [
    `${eventTime(event.date)} UTC · ${words(event.country)} · ${importanceLabel(event.importance)}`,
    event.consensus === null ? "" : `consensus ${formatNumber(event.consensus)}`,
    event.previous === null ? "" : `previous ${formatNumber(event.previous)}`,
  ]
    .filter(Boolean)
    .join("\n");
}

export function filterEvents(events: CalendarEvent[], minImportance: number, economy: string | null): CalendarEvent[] {
  return events.filter((event) => event.importance >= minImportance && (!economy || event.country === economy));
}

export interface CalendarEntry {
  id: string;
  title: string;
  start: string;
  classNames: string[];
  extendedProps: { country: string; importance: number; details: string };
}

export function calendarEntries(events: CalendarEvent[]): CalendarEntry[] {
  return events.map((event) => ({
    id: event.id,
    title: event.event,
    start: event.date,
    classNames: [`importance-${event.importance}`],
    extendedProps: { country: words(event.country), importance: event.importance, details: eventDetails(event) },
  }));
}
