// @vitest-environment happy-dom
// The shell mounts with PrimeVue, the router and a stubbed client: catches wiring mistakes
// that the type checker cannot see (theme config, plugin registration, missing provides).
import { definePreset } from "@primeuix/themes";
import Aura from "@primeuix/themes/aura";
import { flushPromises, mount } from "@vue/test-utils";
import PrimeVue from "primevue/config";
import Tooltip from "primevue/tooltip";
import { expect, test } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import App from "../App.vue";
import type { Client } from "../api/client";
import OverviewPage from "../pages/OverviewPage.vue";

test("the shell renders the navigation, the backend health and the overview", async () => {
  const client = {
    health: async () => ({ status: "ok", last_run: "2026-09-19" }),
    overview: async () => [],
  } as unknown as Client;
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: OverviewPage }] });
  const wrapper = mount(App, {
    global: {
      plugins: [router, [PrimeVue, { theme: { preset: definePreset(Aura, {}), options: { darkModeSelector: '[data-theme="dark"]' } } }]],
      directives: { tooltip: Tooltip },
      provide: { client },
      stubs: { PlotlyChart: true },
    },
  });
  await router.isReady();
  await flushPromises();
  expect(wrapper.text()).toContain("Overview");
  expect(wrapper.text()).toContain("Events");
  expect(wrapper.text()).toContain("last run 19 Sep 2026");
  expect(wrapper.text()).toContain("No score yet");
  expect(document.documentElement.dataset.theme).toMatch(/light|dark/);
});
