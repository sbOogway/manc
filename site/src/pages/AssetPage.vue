<script setup lang="ts">
import Message from "primevue/message";
import Select from "primevue/select";
import SelectButton from "primevue/selectbutton";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import { computed, onMounted, ref, watch } from "vue";

import type { AssetHistory, CalendarEvent, ChainSeries, ForecastPanel, HeadlineView } from "../api/types";
import ChainPanel from "../components/ChainPanel.vue";
import ForecastsPanel from "../components/ForecastsPanel.vue";
import HeadlinesPanel from "../components/HeadlinesPanel.vue";
import PlotlyChart from "../components/PlotlyChart.vue";
import PriceChart from "../components/PriceChart.vue";
import ReportPanel from "../components/ReportPanel.vue";
import UpcomingEvents from "../components/UpcomingEvents.vue";
import { EVENTS_AHEAD_DAYS, RANGE_PRESETS, eventsFor, rangeFor, reportDay } from "../lib/asset";
import { componentsFigure, scoreFigure } from "../lib/charts";
import { useClient } from "../lib/client";
import { bandLabel, formatDate, formatScore, isoDay, shiftDays } from "../lib/format";
import { useTokens } from "../lib/tokens";

const props = defineProps<{ symbol: string }>();
const client = useClient();
const tokens = useTokens();
const today = isoDay(new Date());

const days = ref<number>(90);
const formula = ref<string | null>(null);
const formulas = ref<string[]>([]);
const history = ref<AssetHistory | null>(null);
const events = ref<CalendarEvent[]>([]);
const economies = ref<string[]>([]);
const tradingview = ref<string | null>(null);
const chain = ref<ChainSeries[]>([]);
const report = ref<{ markdown: string | null; day: string | null; note: string }>({ markdown: null, day: null, note: "" });
const headlines = ref<HeadlineView[]>([]);
const panel = ref<ForecastPanel | null>(null);
const error = ref<string | null>(null);

const presets = RANGE_PRESETS.map((preset) => ({ label: `${preset}d`, value: preset }));
const latest = computed(() => history.value?.points.at(-1));
const upcoming = computed(() => eventsFor(events.value, economies.value, today));
const scoreChart = computed(() =>
  history.value ? scoreFigure(history.value, events.value.filter((event) => event.importance === 3), tokens.value) : null,
);
const componentsChart = computed(() => (history.value ? componentsFigure(history.value, tokens.value) : null));

async function loadHistory(): Promise<void> {
  const range = rangeFor(days.value, today);
  history.value = await client.scores(props.symbol, { formula: formula.value, ...range });
  chain.value = await client.chain(props.symbol, range);
  const eventRange = { from: range.from, to: shiftDays(today, EVENTS_AHEAD_DAYS), min_importance: 2 };
  events.value = eventsFor(await client.events(eventRange), economies.value, range.from, 400);
}

async function loadReport(): Promise<void> {
  const day = reportDay(history.value, today);
  try {
    const answer = await client.report(props.symbol, { formula: formula.value, date: day });
    report.value = { markdown: answer.report_md, day, note: "" };
  } catch (failure) {
    report.value = { markdown: null, day, note: (failure as Error).message };
  }
  headlines.value = await client.headlines(props.symbol, { date: day });
}

async function load(): Promise<void> {
  error.value = null;
  history.value = null;
  try {
    const [assets, known] = await Promise.all([client.assets(), client.formulas()]);
    const asset = assets.find((candidate) => candidate.symbol === props.symbol);
    if (!asset) throw new Error(`unknown asset ${props.symbol}`);
    economies.value = asset.economies;
    tradingview.value = asset.tradingview;
    formulas.value = known.known;
    formula.value = formula.value ?? known.default;
    await Promise.all([
      loadHistory().then(loadReport),
      client.forecasts(props.symbol).then((rows) => (panel.value = rows)),
    ]);
  } catch (failure) {
    error.value = (failure as Error).message;
  }
}

onMounted(load);
watch(() => props.symbol, load);
watch(days, loadHistory);
watch(formula, (_value, previous) => {
  if (previous !== null) loadHistory().then(loadReport);
});
</script>

<template>
  <section class="asset">
    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    <header class="asset-head">
      <h1>{{ symbol }}</h1>
      <template v-if="latest">
        <span class="hero small" :style="{ color: 'var(--band-' + latest.band + ')' }">{{ formatScore(latest.score) }}</span>
        <Tag :value="bandLabel(latest.band)" class="band-tag" :style="{ '--band-color': 'var(--band-' + latest.band + ')' }" />
        <span class="muted">{{ formatDate(latest.date) }} · {{ latest.n_news }} headlines · {{ latest.n_events }} events</span>
      </template>
      <span class="spacer"></span>
      <div class="selectors">
        <SelectButton v-model="days" :options="presets" option-label="label" option-value="value" :allow-empty="false" size="small" />
        <Select v-model="formula" :options="formulas" size="small" aria-label="formula" />
      </div>
    </header>

    <div class="charts">
      <div class="card chart-card">
        <Skeleton v-if="history === null" height="30rem" />
        <template v-else>
          <p v-if="!history.points.length" class="muted">No score in this range.</p>
          <PlotlyChart v-if="scoreChart" :figure="scoreChart" />
          <PlotlyChart v-if="componentsChart" :figure="componentsChart" />
        </template>
      </div>
      <PriceChart :symbol="symbol" :ticker="tradingview" />
    </div>

    <ChainPanel :series="chain" />

    <div class="columns">
      <ReportPanel :markdown="report.markdown" :day="report.day" :note="report.note" />
      <div class="stack">
        <UpcomingEvents :events="upcoming" />
        <HeadlinesPanel :headlines="headlines" :day="report.day" />
      </div>
    </div>

    <ForecastsPanel v-if="panel" :panel="panel" :symbol="symbol" />
  </section>
</template>
