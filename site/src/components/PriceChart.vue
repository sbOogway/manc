<script setup lang="ts">
import { computed } from "vue";

import { tradingViewUrl } from "../lib/asset";
import { useTheme } from "../lib/theme";

const props = defineProps<{ symbol: string; ticker: string | null }>();
const theme = useTheme();
const url = computed(() => tradingViewUrl(props.ticker, theme.resolved.value));
</script>

<template>
  <div v-if="url" class="card chart-card price">
    <h2>Price</h2>
    <iframe :src="url" :title="symbol + ' price on TradingView'" loading="lazy" allowfullscreen></iframe>
  </div>
</template>
