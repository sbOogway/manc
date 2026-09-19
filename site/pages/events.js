// The calendar ahead: the next 30 days across every tracked economy, as a month grid.
import { formatDate, formatNumber, importanceLabel } from "../format.js";

const DAY_MS = 24 * 60 * 60 * 1000;
const WINDOW_DAYS = 30;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function toDate(iso) {
  return new Date(`${iso}T00:00:00Z`);
}

function toIso(date) {
  return date.toISOString().slice(0, 10);
}

function shiftDays(iso, days) {
  return toIso(new Date(toDate(iso).getTime() + days * DAY_MS));
}

function mondayOf(iso) {
  const weekday = (toDate(iso).getUTCDay() + 6) % 7; // Monday 0 … Sunday 6
  return shiftDays(iso, -weekday);
}

export function economiesOf(events) {
  return [...new Set(events.map((event) => event.country))].sort();
}

export function eventTime(iso) {
  return iso.slice(11, 16);
}

export function calendarWeeks(events, today, days = WINDOW_DAYS) {
  const end = shiftDays(today, days);
  const byDay = new Map();
  for (const event of [...events].sort((left, right) => left.date.localeCompare(right.date))) {
    const day = event.date.slice(0, 10);
    if (day < today || day > end) continue;
    byDay.set(day, [...(byDay.get(day) ?? []), event]);
  }
  const weeks = [];
  let day = mondayOf(today);
  const lastSunday = shiftDays(mondayOf(end), 6);
  while (day <= lastSunday) {
    const week = [];
    for (let offset = 0; offset < 7; offset += 1) {
      const date = toDate(day);
      const dayOfMonth = date.getUTCDate();
      week.push({
        day,
        dayOfMonth,
        monthLabel: dayOfMonth === 1 || day === mondayOf(today) ? MONTHS[date.getUTCMonth()] : "",
        today: day === today,
        inWindow: day >= today && day <= end,
        events: byDay.get(day) ?? [],
      });
      day = shiftDays(day, 1);
    }
    weeks.push(week);
  }
  return weeks;
}

export const EventsPage = {
  setup() {
    const { computed, inject, onMounted, ref } = Vue;
    const client = inject("client");
    const today = toIso(new Date());
    const events = ref(null);
    const error = ref(null);
    const minImportance = ref(2);
    const economy = ref("");

    async function load() {
      error.value = null;
      events.value = null;
      try {
        events.value = await client.events({});
      } catch (failure) {
        error.value = failure.message;
        events.value = [];
      }
    }
    const economies = computed(() => economiesOf(events.value ?? []));
    const weeks = computed(() =>
      calendarWeeks(
        (events.value ?? []).filter(
          (event) =>
            event.importance >= minImportance.value && (!economy.value || event.country === economy.value),
        ),
        today,
      ),
    );
    const details = (event) =>
      [
        `${eventTime(event.date)} UTC · ${event.country.replaceAll("_", " ")} · ${importanceLabel(event.importance)}`,
        event.consensus === null ? "" : `consensus ${formatNumber(event.consensus)}`,
        event.previous === null ? "" : `previous ${formatNumber(event.previous)}`,
      ]
        .filter(Boolean)
        .join("\n");
    onMounted(load);
    return { events, error, minImportance, economy, economies, weeks, load, details, eventTime, formatDate, WEEKDAYS };
  },
  template: `
    <section>
      <header class="asset-head">
        <h1>Events ahead</h1>
        <span class="spacer"></span>
        <div class="selectors">
          <button type="button" :class="{ active: minImportance === 1 }" @click="minImportance = 1">all</button>
          <button type="button" :class="{ active: minImportance === 2 }" @click="minImportance = 2">medium+</button>
          <button type="button" :class="{ active: minImportance === 3 }" @click="minImportance = 3">high</button>
          <select v-model="economy" aria-label="economy">
            <option value="">every economy</option>
            <option v-for="name in economies" :key="name" :value="name">{{ name.replaceAll('_', ' ') }}</option>
          </select>
        </div>
      </header>
      <p v-if="error" class="error">{{ error }} <button type="button" @click="load">Retry</button></p>
      <div v-if="events === null" class="skeleton" style="min-height: 20rem"></div>
      <div v-else class="calendar card">
        <div class="calendar-head">
          <span v-for="name in WEEKDAYS" :key="name" class="muted">{{ name }}</span>
        </div>
        <div v-for="week in weeks" :key="week[0].day" class="calendar-week">
          <div v-for="cell in week" :key="cell.day" class="calendar-day" :class="{ out: !cell.inWindow, today: cell.today }">
            <div class="calendar-date">
              <span class="num">{{ cell.dayOfMonth }}</span>
              <span class="muted">{{ cell.monthLabel }}</span>
            </div>
            <ul class="calendar-events">
              <li v-for="event in cell.events" :key="event.id" :title="details(event)" :class="'importance-' + event.importance">
                <span class="dot"></span>
                <span class="when num">{{ eventTime(event.date) }}</span>
                <span class="what">{{ event.event }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  `,
};
