<script setup lang="ts">
// One Plotly figure in a div: redraws when the figure or the theme changes, purges on unmount.
import Plotly from "plotly.js-basic-dist-min";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import type { Figure } from "../lib/charts";
import { useTheme } from "../lib/theme";

const props = defineProps<{ figure: Figure }>();
const element = ref<HTMLDivElement | null>(null);
const theme = useTheme();

function draw(): void {
  if (element.value) Plotly.react(element.value, props.figure.data, props.figure.layout, props.figure.config);
}

onMounted(draw);
watch(() => props.figure, draw);
watch(theme.resolved, () => requestAnimationFrame(draw));
onBeforeUnmount(() => {
  if (element.value) Plotly.purge(element.value);
});
</script>

<template>
  <div ref="element" class="chart"></div>
</template>
