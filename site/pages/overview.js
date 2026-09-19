// One stat tile per asset: hero score coloured by band, delta, sparkline, event risk.
import { bandColor, readTokens, sparkline } from "../charts.js";
import { bandLabel, formatDate, formatDelta, formatScore } from "../format.js";

const RISK_LABELS = [
  [0.75, "heavy week"],
  [0.25, "busy week"],
  [0, "quiet"],
];

const KIND_ORDER = ["forex", "metal", "commodity", "equity_index", "crypto", "bond"];
const KIND_LABELS = {
  all: "all",
  forex: "forex",
  metal: "metals",
  commodity: "commodities",
  equity_index: "equity indices",
  crypto: "crypto",
  bond: "bonds",
};
const KIND_KEY = "manc.kind";

export function kindLabel(kind) {
  return KIND_LABELS[kind] ?? kind.replaceAll("_", " ");
}

export function kindsOf(summaries) {
  const present = new Set(summaries.map((summary) => summary.kind));
  const known = KIND_ORDER.filter((kind) => present.has(kind));
  const others = [...present].filter((kind) => !KIND_ORDER.includes(kind)).sort();
  return [...known, ...others];
}

export function filterByKind(summaries, kind) {
  return kind === "all" ? summaries : summaries.filter((summary) => summary.kind === kind);
}

export function eventRiskLabel(risk) {
  return RISK_LABELS.find(([floor]) => risk >= floor)[1];
}

export function tileModel(summary) {
  const delta = summary.delta;
  return {
    symbol: summary.symbol,
    kind: summary.kind,
    band: summary.band,
    score: formatScore(summary.score),
    bandLabel: bandLabel(summary.band),
    delta: formatDelta(delta),
    deltaClass: !delta ? "flat" : delta > 0 ? "up" : "down",
    date: formatDate(summary.date),
    risk: eventRiskLabel(summary.event_risk),
  };
}

const Tile = {
  props: ["summary"],
  setup(props) {
    const { computed, onMounted, onBeforeUnmount, ref, watch } = Vue;
    const model = computed(() => tileModel(props.summary));
    const plot = ref(null);
    let tokens = readTokens();

    function draw() {
      tokens = readTokens();
      const figure = sparkline(props.summary, tokens);
      Plotly.react(plot.value, figure.data, figure.layout, figure.config);
    }
    const redraw = () => draw();
    onMounted(() => {
      draw();
      window.addEventListener("manc:theme", redraw);
    });
    onBeforeUnmount(() => window.removeEventListener("manc:theme", redraw));
    watch(() => props.summary, draw);

    const accent = computed(() => bandColor(props.summary.band, tokens));
    return { model, plot, accent };
  },
  template: `
    <article class="card tile" :style="{ '--band-color': accent }">
      <header class="tile-head">
        <router-link :to="'/asset/' + model.symbol" class="tile-symbol">{{ model.symbol }}</router-link>
        <span class="muted">{{ model.kind.replaceAll('_', ' ') }}</span>
      </header>
      <div class="tile-score">
        <span class="hero" :style="{ color: accent }">{{ model.score }}</span>
        <span class="tile-meta">
          <span class="badge">{{ model.bandLabel }}</span>
          <span class="num delta" :class="model.deltaClass">{{ model.delta }}</span>
        </span>
      </div>
      <div ref="plot" class="sparkline"></div>
      <footer class="tile-foot muted">
        <span>{{ model.risk }}</span>
        <span>{{ model.date }}</span>
      </footer>
    </article>
  `,
};

export const OverviewPage = {
  components: { Tile },
  setup() {
    const { computed, inject, onMounted, ref, watch } = Vue;
    const client = inject("client");
    const summaries = ref(null);
    const error = ref(null);
    let remembered = "all";
    try {
      remembered = localStorage.getItem(KIND_KEY) || "all";
    } catch {
      // storage unavailable: start on "all"
    }
    const kind = ref(remembered);
    const kinds = computed(() => kindsOf(summaries.value ?? []));
    const shown = computed(() => filterByKind(summaries.value ?? [], kind.value));
    watch(kind, (value) => {
      try {
        localStorage.setItem(KIND_KEY, value);
      } catch {
        // the choice lasts the page
      }
    });

    async function load() {
      error.value = null;
      try {
        summaries.value = await client.overview({});
      } catch (failure) {
        error.value = failure.message;
        summaries.value = [];
      }
    }
    onMounted(load);
    return { summaries, error, load, kind, kinds, shown, kindLabel };
  },
  template: `
    <section>
      <div class="selectors kinds" v-if="summaries && summaries.length">
        <button type="button" :class="{ active: kind === 'all' }" @click="kind = 'all'">all</button>
        <button v-for="name in kinds" :key="name" type="button" :class="{ active: kind === name }" @click="kind = name">{{ kindLabel(name) }}</button>
      </div>
      <p v-if="error" class="error">{{ error }} <button type="button" @click="load">Retry</button></p>
      <div v-if="summaries === null" class="grid">
        <div v-for="index in 12" :key="index" class="skeleton"></div>
      </div>
      <p v-else-if="!summaries.length && !error" class="muted">No score yet. Run <code>manc run</code> first.</p>
      <p v-else-if="!shown.length" class="muted">No {{ kindLabel(kind) }} scored yet.</p>
      <div v-else class="grid">
        <Tile v-for="summary in shown" :key="summary.symbol" :summary="summary" />
      </div>
    </section>
  `,
};
