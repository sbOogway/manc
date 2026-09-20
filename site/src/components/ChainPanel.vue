<script setup lang="ts">
import { computed } from "vue";

import type { ChainSeries } from "../api/types";
import { chainFigures } from "../lib/charts";
import { useTokens } from "../lib/tokens";
import PlotlyChart from "./PlotlyChart.vue";

const props = defineProps<{ series: ChainSeries[]; group: "chain" | "sentiment" }>();
const tokens = useTokens();
const TITLES = { chain: "On-chain", sentiment: "Sentiment" } as const;
const NOTES = {
  chain: "Coin Metrics Community (CC BY-NC 4.0), DefiLlama, Solana RPC. Display only: no formula reads these yet.",
  sentiment: "CoinMarketCap Fear & Greed (market-wide), CoinGecko community votes; both keyless. Display only.",
} as const;
const figures = computed(() => chainFigures(props.series.filter((one) => one.group === props.group), tokens.value));
</script>

<template>
  <div v-if="figures.length" class="card chain-card">
    <h2>{{ TITLES[group] }}</h2>
    <div class="chain-grid">
      <div v-for="figure in figures" :key="figure.metric" class="chain-tile">
        <div class="chain-head">
          <span class="muted">{{ figure.label }}</span>
          <span class="chain-latest num">{{ figure.latest }}</span>
        </div>
        <PlotlyChart :figure="figure" />
      </div>
    </div>
    <p class="muted small">{{ NOTES[group] }}</p>
  </div>
</template>
