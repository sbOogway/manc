<script setup lang="ts">
import Tag from "primevue/tag";
import { computed } from "vue";

import type { AssetSummary } from "../api/types";
import { bandColor, sparkline } from "../lib/charts";
import { kindLabel, tileModel } from "../lib/overview";
import { useTokens } from "../lib/tokens";
import PlotlyChart from "./PlotlyChart.vue";

const props = defineProps<{ summary: AssetSummary }>();
const tokens = useTokens();
const model = computed(() => tileModel(props.summary));
const accent = computed(() => bandColor(props.summary.band, tokens.value));
const figure = computed(() => sparkline(props.summary, tokens.value));
</script>

<template>
  <article class="card tile" :style="{ '--band-color': accent }">
    <header class="tile-head">
      <RouterLink :to="'/asset/' + model.symbol" class="tile-symbol">{{ model.symbol }}</RouterLink>
      <span class="muted">{{ kindLabel(model.kind) }}</span>
    </header>
    <div class="tile-score">
      <span class="hero" :style="{ color: accent }">{{ model.score }}</span>
      <span class="tile-meta">
        <Tag :value="model.bandLabel" class="band-tag" />
        <span class="num delta" :class="model.deltaClass">{{ model.delta }}</span>
      </span>
    </div>
    <PlotlyChart :figure="figure" class="sparkline" />
    <footer class="tile-foot muted">
      <span>{{ model.risk }}</span>
      <span>{{ model.date }}</span>
    </footer>
  </article>
</template>
