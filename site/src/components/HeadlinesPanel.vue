<script setup lang="ts">
import { computed } from "vue";

import type { HeadlineView } from "../api/types";
import { headlineRows } from "../lib/asset";
import { formatDate } from "../lib/format";

const props = defineProps<{ headlines: HeadlineView[]; day: string | null }>();
const rows = computed(() => headlineRows(props.headlines));
</script>

<template>
  <article class="card">
    <h2>
      Headlines behind the score <span v-if="day" class="muted">· {{ formatDate(day) }}</span>
    </h2>
    <p v-if="!rows.length" class="muted">No directional headline in the window.</p>
    <ul v-else class="headlines scroll">
      <li v-for="row in rows" :key="row.url" :class="row.direction > 0 ? 'bull' : 'bear'">
        <div class="headline-line">
          <span class="glyph">{{ row.glyph }}</span>
          <a :href="row.url" target="_blank" rel="noopener">{{ row.title }}</a>
          <span v-tooltip.left="'confidence ' + row.confidence + ' × source weight'" class="num weight">{{ row.weight }}</span>
        </div>
        <div class="weight-bar"><span :style="{ width: row.bar + '%' }"></span></div>
        <span class="muted">{{ row.source }} · {{ row.date }}</span>
      </li>
    </ul>
  </article>
</template>
