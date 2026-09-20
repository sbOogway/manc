// @vitest-environment happy-dom
// Each page mounts against a stubbed client with real-shaped data; charts and the calendar are
// stubbed (they need a layout engine), everything else renders for real.
import { definePreset } from "@primeuix/themes";
import Aura from "@primeuix/themes/aura";
import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import Tooltip from "primevue/tooltip";
import { expect, test } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import type { Client } from "../api/client";
import type { AssetHistory, CalendarEvent, ForecastPanel } from "../api/types";
import AssetPage from "../pages/AssetPage.vue";
import EventsPage from "../pages/EventsPage.vue";

const HISTORY: AssetHistory = {
  symbol: "BTCUSD",
  formula: "v2",
  scale: { low: -100, high: 100, neutral: 0, edges: [-40, -10, 10, 40] },
  points: [{ date: "2026-09-19", score: -9.8, band: "neutral", components: { N: -0.1, S: 0, R: 0.2, D: 0 }, n_news: 12, n_events: 173 }],
};
const EVENT: CalendarEvent = { id: "cpi", date: "2026-09-25T12:30:00Z", country: "united_states", event: "CPI", category: "inflation", importance: 3, consensus: 3.1, previous: 2.9, actual: null };
const PANEL: ForecastPanel = { symbol: "BTCUSD", as_of: "2026-09-19", spot: 115000, rows: [], medians: [], macro: [] };

function globals(client: Partial<Client>) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: { template: "<div />" } }] });
  return {
    plugins: [router, [PrimeVue, { theme: { preset: definePreset(Aura, {}), options: { darkModeSelector: '[data-theme="dark"]' } } }]] as never,
    directives: { tooltip: Tooltip },
    provide: { client },
    stubs: { PlotlyChart: true, FullCalendar: true },
  };
}

test("the asset page shows the latest score, the report summary and the panels", async () => {
  const client: Partial<Client> = {
    assets: async () => [{ symbol: "BTCUSD", kind: "crypto", economies: ["united_states"], tradingview: "BITSTAMP:BTCUSD" }],
    formulas: async () => ({ default: "v2", known: ["v1", "v2"] }),
    scores: async () => HISTORY,
    chain: async () => [
      { metric: "mvrv", label: "MVRV", group: "chain", source: "coinmetrics", points: [{ date: "2026-09-19", value: 1.5 }] },
      { metric: "fear_greed", label: "Fear & Greed (market)", group: "sentiment", source: "coinmarketcap", points: [{ date: "2026-09-19", value: 73 }] },
    ],
    events: async () => [EVENT],
    report: async () => ({ symbol: "BTCUSD", date: "2026-09-19", formula: "v2", report_md: "# BTCUSD 2026-09-19: -10 neutral\n\nQuiet day for bitcoin.\n\n## Components\n\n- N: -0.10\n\n---\n\nSummary by test/model.\n" }),
    headlines: async () => [{ title: "Bitcoin steady", url: "u/1", source: "reuters", published_at: "2026-09-19T08:00:00Z", direction: 1, confidence: 0.7, source_weight: 1, weight: 0.7 }],
    forecasts: async () => PANEL,
  };
  const wrapper = mount(AssetPage, { props: { symbol: "BTCUSD" }, global: globals(client) });
  await flushPromises();
  const text = wrapper.text();
  expect(text).toContain("BTCUSD");
  expect(text).toContain("-10"); // the hero score
  expect(text).toContain("Quiet day for bitcoin.");
  expect(text).toContain("Summary by test/model");
  expect(text).toContain("CPI"); // ahead
  expect(text).toContain("Bitcoin steady"); // headlines
  expect(text).toContain("No institutional forecast stored");
  expect(text).toContain("On-chain");
  expect(text).toContain("Sentiment");
  expect(text).toContain("Fear & Greed (market)");
  expect(wrapper.find("iframe").attributes("src")).toContain("BITSTAMP%3ABTCUSD");
});

test("the events page offers the importance floor and the economies", async () => {
  const client: Partial<Client> = { events: async () => [EVENT, { ...EVENT, id: "ecb", country: "euro_area", importance: 2 }] };
  const wrapper = mount(EventsPage, { global: globals(client) });
  await flushPromises();
  expect(wrapper.text()).toContain("Events ahead");
  expect(wrapper.text()).toContain("medium+");
  expect(wrapper.find("full-calendar-stub, fullcalendar-stub").exists() || wrapper.html().includes("calendar")).toBe(true);
});
