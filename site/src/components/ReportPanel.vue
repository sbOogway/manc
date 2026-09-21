<script setup lang="ts">
import { computed } from "vue";

import { reportParts } from "../lib/asset";
import { formatDate } from "../lib/format";
import { renderMarkdown } from "../lib/markdown";

const props = defineProps<{ markdown: string | null; day: string | null; note: string }>();
const parts = computed(() => reportParts(props.markdown));
const html = computed(() => renderMarkdown(parts.value.rest));
</script>

<template>
  <article class="card report">
    <h2>
      Report <span v-if="day" class="muted">· {{ formatDate(day) }}</span>
    </h2>
    <p v-if="parts.summary" class="summary">{{ parts.summary }}</p>
    <p v-else-if="markdown" class="muted">No summary for this day.</p>
    <p v-if="note" class="muted">{{ note }}</p>
    <p v-if="parts.model" class="muted small">Summary by {{ parts.model }}</p>
    <details v-if="html">
      <summary class="muted">Full report</summary>
      <div class="markdown" v-html="html"></div>
    </details>
  </article>
</template>
