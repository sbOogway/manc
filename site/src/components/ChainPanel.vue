<script setup lang="ts">
import { computed } from "vue";

import type { ChainSeries } from "../api/types";
import { chainFigures } from "../lib/charts";
import { useTokens } from "../lib/tokens";
import PlotlyChart from "./PlotlyChart.vue";

const props = defineProps<{ series: ChainSeries[] }>();
const tokens = useTokens();
const figures = computed(() => chainFigures(props.series, tokens.value));
</script>

<template>
  <div v-if="figures.length" class="card chain-card">
    <h2>On-chain</h2>
    <div class="chain-grid">
      <div v-for="figure in figures" :key="figure.metric" class="chain-tile">
        <div class="chain-head">
          <span class="muted">{{ figure.label }}</span>
          <span class="chain-latest num">{{ figure.latest }}</span>
        </div>
        <PlotlyChart :figure="figure" />
      </div>
    </div>
    <p class="muted small">Display only: no formula reads these yet.</p>
  </div>
</template>
