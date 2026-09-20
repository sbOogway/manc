<script setup lang="ts">
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import Tag from "primevue/tag";

import type { CalendarEvent } from "../api/types";
import { formatDate, importanceLabel, words } from "../lib/format";

defineProps<{ events: CalendarEvent[] }>();

const SEVERITY: Record<number, "danger" | "warn" | "secondary"> = { 3: "danger", 2: "warn", 1: "secondary" };
</script>

<template>
  <article class="card">
    <h2>Ahead</h2>
    <p v-if="!events.length" class="muted">Nothing scheduled in the next two weeks.</p>
    <DataTable v-else :value="events" size="small" scrollable scroll-height="18rem" data-key="id">
      <Column header="Date">
        <template #body="{ data }">{{ formatDate(data.date) }}</template>
      </Column>
      <Column header="Country">
        <template #body="{ data }">{{ words(data.country) }}</template>
      </Column>
      <Column field="event" header="Event" />
      <Column header="Importance">
        <template #body="{ data }">
          <Tag :value="importanceLabel(data.importance)" :severity="SEVERITY[data.importance] ?? 'secondary'" />
        </template>
      </Column>
    </DataTable>
  </article>
</template>
