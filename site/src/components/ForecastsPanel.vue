<script setup lang="ts">
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import { computed } from "vue";

import type { ForecastPanel } from "../api/types";
import { forecastRows, macroRows } from "../lib/asset";
import { formatNumber } from "../lib/format";

const props = defineProps<{ panel: ForecastPanel; symbol: string }>();
const rows = computed(() => forecastRows(props.panel));
const macro = computed(() => macroRows(props.panel.macro));
</script>

<template>
  <article class="card">
    <h2>
      Forecasts <span v-if="panel.spot" class="muted">· spot {{ formatNumber(panel.spot) }}</span>
    </h2>
    <p v-if="!rows.length" class="muted">No institutional forecast stored for {{ symbol }}.</p>
    <DataTable v-else :value="rows" size="small" data-key="key" :row-class="(row: { median: boolean }) => (row.median ? 'median' : '')">
      <Column header="Horizon">
        <template #body="{ data }">{{ data.horizon }} <span class="muted">{{ data.horizonDate }}</span></template>
      </Column>
      <Column field="institution" header="Institution" />
      <Column field="value" header="Target" class="num" />
      <Column field="vsSpot" header="vs spot" class="num" />
      <Column field="revision" header="Revision" />
      <Column field="previous" header="Previous" class="num" />
      <Column field="published" header="Published" />
      <Column field="confidence" header="Conf." class="num" />
    </DataTable>
    <template v-if="macro.length">
      <h3>Macro forecasts for the asset's economies</h3>
      <DataTable :value="macro" size="small" data-key="key">
        <Column field="economy" header="Economy" />
        <Column field="metric" header="Metric" />
        <Column header="Horizon">
          <template #body="{ data }">{{ data.horizon }} <span class="muted">{{ data.horizonDate }}</span></template>
        </Column>
        <Column field="institution" header="Institution" />
        <Column field="value" header="Value" class="num" />
        <Column field="revision" header="Revision" />
        <Column field="previous" header="Previous" class="num" />
        <Column field="published" header="Published" />
      </DataTable>
    </template>
  </article>
</template>
