<script setup lang="ts">
// The calendar ahead: FullCalendar's month and list views over the next weeks, every tracked economy.
import FullCalendar from "@fullcalendar/vue3";
import dayGridPlugin from "@fullcalendar/vue3/daygrid";
import listPlugin from "@fullcalendar/vue3/list";
import classicThemePlugin from "@fullcalendar/vue3/themes/classic";
import Message from "primevue/message";
import Select from "primevue/select";
import SelectButton from "primevue/selectbutton";
import Skeleton from "primevue/skeleton";
import { computed, onMounted, ref } from "vue";

import "@fullcalendar/vue3/skeleton.css";
import "@fullcalendar/vue3/themes/classic/theme.css";
import "@fullcalendar/vue3/themes/classic/palette.css";

import type { CalendarOptions } from "@fullcalendar/vue3";

import type { CalendarEvent } from "../api/types";
import { useClient } from "../lib/client";
import { IMPORTANCE_CHOICES, calendarEntries, economiesOf, eventTime, filterEvents } from "../lib/events";
import { isoDay, shiftDays, words } from "../lib/format";

const WINDOW_DAYS = 60;
const client = useClient();
const today = isoDay(new Date());
const events = ref<CalendarEvent[] | null>(null);
const error = ref<string | null>(null);
const minImportance = ref<number>(2);
const economy = ref<string | null>(null);

async function load(): Promise<void> {
  error.value = null;
  events.value = null;
  try {
    events.value = await client.events({ from: shiftDays(today, -7), to: shiftDays(today, WINDOW_DAYS) });
  } catch (failure) {
    error.value = (failure as Error).message;
    events.value = [];
  }
}

const economies = computed(() => economiesOf(events.value ?? []).map((name) => ({ name, label: words(name) })));
const entries = computed(() => calendarEntries(filterEvents(events.value ?? [], minImportance.value, economy.value)));
const options = computed<CalendarOptions>(() => ({
  plugins: [classicThemePlugin, dayGridPlugin, listPlugin],
  initialView: "dayGridMonth",
  headerToolbar: { start: "title", center: "", end: "today prev,next dayGridMonth,listMonth" },
  firstDay: 1,
  timeZone: "UTC",
  height: "auto",
  dayMaxEvents: 6,
  eventTimeFormat: { hour: "2-digit", minute: "2-digit", hour12: false } as const,
  events: entries.value,
  eventDidMount: (info) => {
    info.el.title = String(info.event.extendedProps.details ?? "");
  },
}));

onMounted(load);
</script>

<template>
  <section>
    <header class="asset-head">
      <h1>Events ahead</h1>
      <span class="spacer"></span>
      <div class="selectors">
        <SelectButton v-model="minImportance" :options="[...IMPORTANCE_CHOICES]" option-label="label" option-value="value" :allow-empty="false" size="small" />
        <Select v-model="economy" :options="economies" option-label="label" option-value="name" placeholder="every economy" show-clear size="small" aria-label="economy" />
      </div>
    </header>
    <Message v-if="error" severity="error" :closable="false">
      {{ error }} <a href="#" @click.prevent="load">Retry</a>
    </Message>
    <Skeleton v-if="events === null" height="24rem" />
    <div v-else class="card calendar">
      <FullCalendar :options="options">
        <template #eventContent="{ event, timeText }">
          <span class="fc-when num">{{ timeText || eventTime(event.startStr) }}</span>
          <span class="fc-what">{{ event.title }}</span>
          <span class="fc-where muted">{{ event.extendedProps.country }}</span>
        </template>
      </FullCalendar>
    </div>
  </section>
</template>
