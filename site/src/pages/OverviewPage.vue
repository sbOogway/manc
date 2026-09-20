<script setup lang="ts">
import Message from "primevue/message";
import SelectButton from "primevue/selectbutton";
import Skeleton from "primevue/skeleton";
import { computed, onMounted, ref, watch } from "vue";

import type { AssetSummary } from "../api/types";
import ScoreTile from "../components/ScoreTile.vue";
import { useClient } from "../lib/client";
import { KIND_KEY, filterByKind, kindLabel, kindsOf } from "../lib/overview";

const client = useClient();
const summaries = ref<AssetSummary[] | null>(null);
const error = ref<string | null>(null);

function rememberedKind(): string {
  try {
    return localStorage.getItem(KIND_KEY) || "all";
  } catch {
    return "all";
  }
}
const kind = ref(rememberedKind());
const kinds = computed(() => ["all", ...kindsOf(summaries.value ?? [])].map((name) => ({ name, label: kindLabel(name) })));
const shown = computed(() => filterByKind(summaries.value ?? [], kind.value));
watch(kind, (value) => {
  try {
    localStorage.setItem(KIND_KEY, value);
  } catch {
    // the choice lasts the page
  }
});

async function load(): Promise<void> {
  error.value = null;
  try {
    summaries.value = await client.overview();
  } catch (failure) {
    error.value = (failure as Error).message;
    summaries.value = [];
  }
}
onMounted(load);
</script>

<template>
  <section>
    <div v-if="summaries && summaries.length" class="selectors">
      <SelectButton v-model="kind" :options="kinds" option-label="label" option-value="name" :allow-empty="false" size="small" />
    </div>
    <Message v-if="error" severity="error" :closable="false">
      {{ error }} <a href="#" @click.prevent="load">Retry</a>
    </Message>
    <div v-if="summaries === null" class="grid">
      <Skeleton v-for="index in 8" :key="index" height="11rem" />
    </div>
    <p v-else-if="!summaries.length && !error" class="muted">No score yet. Run <code>manc run</code> first.</p>
    <p v-else-if="!shown.length" class="muted">No {{ kindLabel(kind) }} scored yet.</p>
    <div v-else class="grid">
      <ScoreTile v-for="summary in shown" :key="summary.symbol" :summary="summary" />
    </div>
  </section>
</template>
