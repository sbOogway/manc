// One asset: score history, components, report, events ahead, headlines, forecasts.
import { CHART_CONFIG, bandColor, layoutTemplate, readTokens } from "../charts.js";
import { BANDS, bandLabel, formatDate, formatNumber, formatPercent, formatScore, importanceLabel } from "../format.js";

export const RANGE_PRESETS = [30, 90, 180, 365];
export const COMPONENT_COLORS = { N: "#eb6834", S: "#1baf7a", R: "#eda100", D: "#e87ba4" }; // categorical slots 2-5
const COMPONENT_NAMES = { N: "news", S: "surprise", R: "event risk", D: "dispersion" };
const EVENTS_AHEAD_DAYS = 14;
const DAY_MS = 24 * 60 * 60 * 1000;

function isoDay(date) {
  return date.toISOString().slice(0, 10);
}

function shiftDays(iso, days) {
  return isoDay(new Date(new Date(`${iso}T00:00:00Z`).getTime() + days * DAY_MS));
}

export function themeName(chosen, prefersDark) {
  return chosen === "dark" || chosen === "light" ? chosen : prefersDark ? "dark" : "light";
}

export function tradingViewUrl(symbol, theme) {
  // TradingView's own widget iframe, daily candles, no toolbar: the price next to the score.
  if (!symbol) return null;
  const params = new URLSearchParams({
    symbol,
    interval: "D",
    theme,
    style: "1",
    locale: "en",
    timezone: "Etc/UTC",
    hide_top_toolbar: "1",
    hidesidetoolbar: "1",
    symboledit: "0",
    saveimage: "0",
    withdateranges: "1",
    hideideas: "1",
  });
  return `https://s.tradingview.com/widgetembed/?${params}`;
}

function currentTheme() {
  const chosen = globalThis.document?.documentElement.dataset.theme;
  const prefersDark = globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  return themeName(chosen, prefersDark);
}

function rgba(hex, alpha) {
  const [red, green, blue] = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16));
  return `rgba(${red},${green},${blue},${alpha})`;
}

export function rangeFor(days, today = isoDay(new Date())) {
  return { from: shiftDays(today, -days), to: today };
}

function componentText(components) {
  return Object.entries(components)
    .map(([name, value]) => `${name} ${value.toFixed(2)}`)
    .join(" · ");
}

export function scoreFigure(history, events, tokens) {
  const points = history.points;
  const scale = history.scale;
  const floors = [scale.low, ...scale.edges, scale.high];
  const dates = points.map((point) => point.date);
  const byDay = new Map();
  for (const event of events) {
    const day = event.date.slice(0, 10);
    byDay.set(day, [...(byDay.get(day) ?? []), event.event]);
  }
  const eventDays = [...byDay.keys()].sort();
  const data = [
    {
      type: "scatter",
      mode: "lines",
      name: "score",
      x: dates,
      y: points.map((point) => point.score),
      text: points.map((point) => componentText(point.components)),
      hovertemplate: "%{x}<br><b>%{y:.1f}</b><br>%{text}<extra></extra>",
      fill: "tozeroy",
      fillcolor: rgba(tokens.accent, 0.08),
      line: { color: tokens.accent, width: 2 },
    },
    {
      type: "scatter",
      mode: "markers",
      name: "events",
      x: eventDays,
      y: eventDays.map(() => scale.low + 0.02 * (scale.high - scale.low)),
      text: eventDays.map((day) => byDay.get(day).join(" · ")),
      hovertemplate: "%{x}<br>%{text}<extra></extra>",
      marker: { color: tokens.muted, size: 8, symbol: "diamond" },
    },
  ];
  const shapes = BANDS.map((band, index) => ({
    name: "band",
    type: "rect",
    xref: "paper",
    x0: 0,
    x1: 1,
    y0: floors[index],
    y1: floors[index + 1],
    fillcolor: rgba(bandColor(band, tokens), tokens.bandFillAlpha),
    line: { width: 0 },
    layer: "below",
  }));
  shapes.push({
    name: "neutral",
    type: "line",
    xref: "paper",
    x0: 0,
    x1: 1,
    y0: scale.neutral,
    y1: scale.neutral,
    line: { color: tokens.axis, width: 1, dash: "dot" },
    layer: "below",
  });
  for (const day of eventDays) {
    shapes.push({
      name: "event",
      type: "line",
      x0: day,
      x1: day,
      yref: "paper",
      y0: 0,
      y1: 1,
      line: { color: tokens.axis, width: 1 },
      layer: "below",
    });
  }
  const template = layoutTemplate(tokens);
  const layout = {
    ...template,
    height: 320,
    hovermode: "x unified",
    yaxis: { ...template.yaxis, range: [scale.low, scale.high], tickvals: floors, showgrid: false },
    xaxis: { ...template.xaxis, showgrid: false },
    shapes,
  };
  return { data, layout, config: CHART_CONFIG };
}

export function componentsFigure(history, tokens) {
  const points = history.points;
  const names = points.length ? Object.keys(points[0].components) : [];
  const data = names.map((name) => ({
    type: "scatter",
    mode: "lines",
    name,
    x: points.map((point) => point.date),
    y: points.map((point) => point.components[name]),
    line: { color: COMPONENT_COLORS[name] ?? tokens.muted, width: 2 },
    hovertemplate: `${COMPONENT_NAMES[name] ?? name} %{y:.2f}<extra></extra>`,
  }));
  const last = points.length - 1;
  const annotations = names.map((name) => ({
    text: name,
    x: points[last].date,
    y: points[last].components[name],
    xanchor: "left",
    showarrow: false,
    font: { color: COMPONENT_COLORS[name] ?? tokens.muted, size: 11 },
  }));
  const template = layoutTemplate(tokens);
  const layout = {
    ...template,
    height: 160,
    hovermode: "x unified",
    margin: { ...template.margin, r: 24, t: 4 },
    yaxis: { ...template.yaxis, range: [-1.05, 1.05], tickvals: [-1, 0, 1], zeroline: true },
    xaxis: { ...template.xaxis, showgrid: false },
    annotations,
  };
  return { data, layout, config: CHART_CONFIG };
}

export function eventsFor(events, economies, today, days = EVENTS_AHEAD_DAYS) {
  const end = shiftDays(today, days);
  return events.filter((event) => {
    const day = event.date.slice(0, 10);
    return economies.includes(event.country) && day > today && day <= end;
  });
}

export function reportParts(markdown) {
  const parts = { title: "", summary: "", model: "", rest: "" };
  if (!markdown) return parts;
  const footer = markdown.match(/\n---\n\nSummary by (.+?)\.\n?$/);
  const body = footer ? markdown.slice(0, footer.index) : markdown;
  parts.model = footer ? footer[1] : "";
  const firstSection = body.indexOf("\n## ");
  const head = firstSection === -1 ? body : body.slice(0, firstSection);
  parts.rest = firstSection === -1 ? "" : body.slice(firstSection + 1).trim();
  const [title, ...paragraphs] = head.split("\n\n");
  parts.title = title.replace(/^#\s*/, "").trim();
  parts.summary = paragraphs.join("\n\n").trim();
  return parts;
}

export function reportDay(history, today) {
  return history?.points?.at(-1)?.date ?? today;
}

export function headlineRows(headlines) {
  const strongest = Math.max(0, ...headlines.map((headline) => headline.weight));
  return headlines.map((headline) => ({
    title: headline.title,
    url: headline.url,
    source: headline.source,
    date: formatDate(headline.published_at),
    direction: headline.direction,
    glyph: headline.direction > 0 ? "▲" : "▼",
    weight: headline.weight.toFixed(2),
    confidence: headline.confidence.toFixed(2),
    bar: strongest > 0 ? (100 * headline.weight) / strongest : 0,
  }));
}

export function revision(row) {
  if (row.previous_value === null || row.previous_value === undefined) return "—";
  if (row.value > row.previous_value) return "▲";
  if (row.value < row.previous_value) return "▼";
  return "—";
}

export function forecastRows(panel) {
  const groups = new Map();
  for (const row of panel.rows) {
    const group = groups.get(row.horizon_date) ?? { horizon: row.horizon_date, label: row.horizon_label, rows: [] };
    group.rows.push({
      institution: row.institution.replaceAll("_", " "),
      value: formatNumber(row.value),
      vsSpot: formatPercent(row.vs_spot),
      revision: revision(row),
      previous: formatNumber(row.previous_value),
      published: formatDate(row.published_at),
      confidence: row.confidence.toFixed(2),
    });
    groups.set(row.horizon_date, group);
  }
  for (const median of panel.medians) {
    const group = groups.get(median.horizon_date);
    if (!group) continue;
    group.median = {
      value: median.value,
      text: formatNumber(median.value),
      vsSpot: panel.spot ? formatPercent(median.value / panel.spot - 1) : "—",
    };
  }
  return [...groups.values()].sort((left, right) => left.horizon.localeCompare(right.horizon));
}

export const AssetPage = {
  props: ["symbol"],
  setup(props) {
    const { inject, onBeforeUnmount, onMounted, ref, watch } = Vue;
    const client = inject("client");
    const today = isoDay(new Date());
    const days = ref(90);
    const formula = ref(null);
    const formulas = ref([]);
    const history = ref(null);
    const events = ref([]);
    const economies = ref([]);
    const report = ref({ summary: "", model: "", html: "", note: "", day: null });
    const headlines = ref([]);
    const panel = ref(null);
    const error = ref(null);
    const scorePlot = ref(null);
    const componentsPlot = ref(null);
    const tradingview = ref(null);
    const theme = ref(currentTheme());

    function draw() {
      theme.value = currentTheme();
      if (!history.value || !scorePlot.value) return;
      const tokens = readTokens();
      const score = scoreFigure(history.value, events.value.filter((event) => event.importance === 3), tokens);
      Plotly.react(scorePlot.value, score.data, score.layout, score.config);
      const components = componentsFigure(history.value, tokens);
      Plotly.react(componentsPlot.value, components.data, components.layout, components.config);
    }

    async function loadHistory() {
      const range = rangeFor(days.value, today);
      history.value = await client.scores(props.symbol, { formula: formula.value, ...range });
      const eventRange = { from: range.from, to: shiftDays(today, EVENTS_AHEAD_DAYS), min_importance: 2 };
      events.value = eventsFor(await client.events(eventRange), economies.value, range.from, 400);
      draw();
    }

    async function loadReport() {
      const day = reportDay(history.value, today);
      try {
        const answer = await client.report(props.symbol, { formula: formula.value, date: day });
        const parts = reportParts(answer.report_md);
        report.value = {
          summary: parts.summary,
          model: parts.model,
          html: marked.parse(parts.rest),
          note: parts.summary ? "" : "No summary for this day.",
          day,
        };
      } catch (failure) {
        report.value = { summary: "", model: "", html: "", note: failure.message, day };
      }
      headlines.value = await client.headlines(props.symbol, { date: day });
    }

    async function load() {
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
          client.forecasts(props.symbol, {}).then((rows) => (panel.value = rows)),
        ]);
      } catch (failure) {
        error.value = failure.message;
      }
    }

    const redraw = () => draw();
    onMounted(() => {
      load();
      window.addEventListener("manc:theme", redraw);
    });
    onBeforeUnmount(() => window.removeEventListener("manc:theme", redraw));
    watch(() => props.symbol, load);
    watch(days, loadHistory);
    watch(formula, (value, previous) => {
      if (previous !== null) loadHistory().then(loadReport);
    });

    return {
      today,
      days,
      formula,
      formulas,
      history,
      report,
      headlines,
      panel,
      error,
      scorePlot,
      componentsPlot,
      RANGE_PRESETS,
      priceUrl: () => tradingViewUrl(tradingview.value, theme.value),
      upcoming: () => eventsFor(events.value, economies.value, today),
      latest: () => history.value?.points.at(-1),
      groups: () => (panel.value ? forecastRows(panel.value) : []),
      headlineRows,
      importanceLabel,
      bandLabel,
      formatDate,
      formatNumber,
      formatScore,
    };
  },
  template: `
    <section class="asset">
      <p v-if="error" class="error">{{ error }}</p>
      <header class="asset-head">
        <h1>{{ symbol }}</h1>
        <template v-if="latest()">
          <span class="hero small" :style="{ color: 'var(--band-' + latest().band + ')' }">{{ formatScore(latest().score) }}</span>
          <span class="badge" :style="{ '--band-color': 'var(--band-' + latest().band + ')' }">{{ bandLabel(latest().band) }}</span>
          <span class="muted">{{ formatDate(latest().date) }} · {{ latest().n_news }} headlines · {{ latest().n_events }} events</span>
        </template>
        <span class="spacer"></span>
        <div class="selectors">
          <button v-for="preset in RANGE_PRESETS" :key="preset" type="button" :class="{ active: days === preset }" @click="days = preset">{{ preset }}d</button>
          <select v-model="formula" aria-label="formula">
            <option v-for="name in formulas" :key="name" :value="name">{{ name }}</option>
          </select>
        </div>
      </header>

      <div class="charts">
        <div class="card chart-card">
          <div v-if="history === null" class="skeleton" style="min-height: 480px"></div>
          <template v-else>
            <p v-if="!history.points.length" class="muted">No score in this range.</p>
            <div ref="scorePlot" class="chart"></div>
            <div ref="componentsPlot" class="chart"></div>
          </template>
        </div>
        <div v-if="priceUrl()" class="card chart-card price">
          <h2>Price</h2>
          <iframe :src="priceUrl()" :title="symbol + ' price on TradingView'" loading="lazy" allowfullscreen></iframe>
        </div>
      </div>

      <div class="columns">
        <article class="card report">
          <h2>Report <span class="muted" v-if="report.day">· {{ formatDate(report.day) }}</span></h2>
          <p v-if="report.summary" class="summary">{{ report.summary }}</p>
          <p v-if="report.note" class="muted">{{ report.note }}</p>
          <p v-if="report.model" class="muted small">Summary by {{ report.model }}</p>
          <details v-if="report.html">
            <summary class="muted">Full report</summary>
            <div v-html="report.html"></div>
          </details>
        </article>

        <div class="stack">
          <article class="card">
            <h2>Ahead</h2>
            <p v-if="!upcoming().length" class="muted">Nothing scheduled in the next two weeks.</p>
            <div v-else class="scroll">
            <table>
              <thead><tr><th>Date</th><th>Country</th><th>Event</th><th>Importance</th></tr></thead>
              <tbody>
                <tr v-for="event in upcoming()" :key="event.id">
                  <td class="num">{{ formatDate(event.date) }}</td>
                  <td>{{ event.country.replaceAll('_', ' ') }}</td>
                  <td>{{ event.event }}</td>
                  <td><span class="badge" :class="'importance-' + event.importance">{{ importanceLabel(event.importance) }}</span></td>
                </tr>
              </tbody>
            </table>
            </div>
          </article>

          <article class="card">
            <h2>Headlines behind the score <span class="muted" v-if="report.day">· {{ formatDate(report.day) }}</span></h2>
            <p v-if="!headlines.length" class="muted">No directional headline in the window.</p>
            <ul v-else class="headlines scroll">
              <li v-for="row in headlineRows(headlines)" :key="row.url" :class="row.direction > 0 ? 'bull' : 'bear'">
                <div class="headline-line">
                  <span class="glyph">{{ row.glyph }}</span>
                  <a :href="row.url" target="_blank" rel="noopener">{{ row.title }}</a>
                  <span class="num weight" :title="'confidence ' + row.confidence + ' × source weight'">{{ row.weight }}</span>
                </div>
                <div class="weight-bar"><span :style="{ width: row.bar + '%' }"></span></div>
                <span class="muted">{{ row.source }} · {{ row.date }}</span>
              </li>
            </ul>
          </article>
        </div>
      </div>

      <article class="card" v-if="panel">
        <h2>Forecasts <span class="muted" v-if="panel.spot">· spot {{ formatNumber(panel.spot) }}</span></h2>
        <p v-if="!groups().length" class="muted">No institutional forecast stored for {{ symbol }}.</p>
        <table v-else>
          <thead><tr><th>Horizon</th><th>Institution</th><th class="num">Target</th><th class="num">vs spot</th><th>Revision</th><th class="num">Previous</th><th>Published</th><th class="num">Conf.</th></tr></thead>
          <tbody>
            <template v-for="group in groups()" :key="group.horizon">
              <tr v-for="row in group.rows" :key="group.horizon + row.institution">
                <td>{{ group.label }} <span class="muted">{{ formatDate(group.horizon) }}</span></td>
                <td>{{ row.institution }}</td>
                <td class="num">{{ row.value }}</td>
                <td class="num">{{ row.vsSpot }}</td>
                <td>{{ row.revision }}</td>
                <td class="num">{{ row.previous }}</td>
                <td>{{ row.published }}</td>
                <td class="num">{{ row.confidence }}</td>
              </tr>
              <tr v-if="group.median" class="median">
                <td>{{ group.label }}</td>
                <td>median</td>
                <td class="num">{{ group.median.text }}</td>
                <td class="num">{{ group.median.vsSpot }}</td>
                <td colspan="4"></td>
              </tr>
            </template>
          </tbody>
        </table>
        <h3 v-if="panel.macro.length">Macro forecasts for the asset's economies</h3>
        <table v-if="panel.macro.length">
          <thead><tr><th>Economy</th><th>Metric</th><th>Horizon</th><th>Institution</th><th class="num">Value</th><th>Revision</th><th class="num">Previous</th><th>Published</th></tr></thead>
          <tbody>
            <tr v-for="row in panel.macro" :key="row.institution + row.economy + row.metric + row.horizon_date">
              <td>{{ row.economy.replaceAll('_', ' ') }}</td>
              <td>{{ row.metric.replaceAll('_', ' ') }}</td>
              <td>{{ row.horizon_label }} <span class="muted">{{ formatDate(row.horizon_date) }}</span></td>
              <td>{{ row.institution.replaceAll('_', ' ') }}</td>
              <td class="num">{{ formatNumber(row.value) }}</td>
              <td>{{ row.previous_value === null ? '—' : row.value > row.previous_value ? '▲' : row.value < row.previous_value ? '▼' : '—' }}</td>
              <td class="num">{{ formatNumber(row.previous_value) }}</td>
              <td>{{ formatDate(row.published_at) }}</td>
            </tr>
          </tbody>
        </table>
      </article>
    </section>
  `,
};
