// The calendar ahead: the next 30 days across every tracked economy.
import { formatDate, formatNumber, importanceLabel } from "../format.js";

export function groupByDay(events) {
  const groups = [];
  for (const event of events) {
    const day = event.date.slice(0, 10);
    const last = groups.at(-1);
    if (last && last.day === day) {
      last.events.push(event);
    } else {
      groups.push({ day, events: [event] });
    }
  }
  return groups;
}

export function economiesOf(events) {
  return [...new Set(events.map((event) => event.country))].sort();
}

export function eventTime(iso) {
  return iso.slice(11, 16);
}

export const EventsPage = {
  setup() {
    const { computed, inject, onMounted, ref } = Vue;
    const client = inject("client");
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
    const groups = computed(() =>
      groupByDay(
        (events.value ?? []).filter(
          (event) =>
            event.importance >= minImportance.value && (!economy.value || event.country === economy.value),
        ),
      ),
    );
    onMounted(load);
    return { events, error, minImportance, economy, economies, groups, load, formatDate, formatNumber, importanceLabel, eventTime };
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
      <p v-else-if="!groups.length" class="muted">Nothing scheduled for this filter.</p>
      <article v-else class="card">
        <table>
          <thead><tr><th>Time (UTC)</th><th>Country</th><th>Event</th><th>Importance</th><th class="num">Consensus</th><th class="num">Previous</th></tr></thead>
          <tbody>
            <template v-for="group in groups" :key="group.day">
              <tr class="day"><th colspan="6">{{ formatDate(group.day) }}</th></tr>
              <tr v-for="event in group.events" :key="event.id">
                <td class="num">{{ eventTime(event.date) }}</td>
                <td>{{ event.country.replaceAll('_', ' ') }}</td>
                <td>{{ event.event }}</td>
                <td><span class="badge" :class="'importance-' + event.importance">{{ importanceLabel(event.importance) }}</span></td>
                <td class="num">{{ formatNumber(event.consensus) }}</td>
                <td class="num">{{ formatNumber(event.previous) }}</td>
              </tr>
            </template>
          </tbody>
        </table>
      </article>
    </section>
  `,
};
