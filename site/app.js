// The shell: header with the backend field and the theme toggle, the router, the pages.
import { apiUrl, createClient, setApiUrl } from "./client.js";
import { formatDate } from "./format.js";
import { AssetPage } from "./pages/asset.js";
import { EventsPage } from "./pages/events.js";
import { OverviewPage } from "./pages/overview.js";

const { createApp, ref, provide } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

const THEME_KEY = "manc.theme";
const THEMES = ["auto", "light", "dark"];

function readTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || "auto";
  } catch {
    return "auto";
  }
}

function applyTheme(theme) {
  if (theme === "auto") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // storage unavailable: the choice lasts the page
  }
}

const Shell = {
  setup() {
    const client = createClient();
    const backend = ref(apiUrl());
    const health = ref({ state: "checking", text: "checking…" });
    const theme = ref(readTheme());
    applyTheme(theme.value);

    async function check() {
      health.value = { state: "checking", text: "checking…" };
      try {
        const answer = await client.health();
        const lastRun = answer.last_run ? `last run ${formatDate(answer.last_run)}` : "no run yet";
        health.value = { state: "ok", text: lastRun };
      } catch (error) {
        health.value = { state: "down", text: error.message };
      }
    }

    function applyBackend() {
      setApiUrl(backend.value);
      backend.value = apiUrl();
      check();
    }

    function cycleTheme() {
      theme.value = THEMES[(THEMES.indexOf(theme.value) + 1) % THEMES.length];
      applyTheme(theme.value);
      window.dispatchEvent(new CustomEvent("manc:theme"));
    }

    provide("client", client);
    check();
    return { backend, health, theme, applyBackend, cycleTheme };
  },
  template: `
    <div class="shell">
      <header class="topbar">
        <router-link class="brand" to="/">manc</router-link>
        <nav class="nav">
          <router-link to="/">Overview</router-link>
          <router-link to="/events">Events</router-link>
        </nav>
        <span class="spacer"></span>
        <form class="backend" @submit.prevent="applyBackend">
          <span class="status-dot" :class="health.state" :title="health.text"></span>
          <span class="ink-2">{{ health.text }}</span>
          <input v-model="backend" type="url" placeholder="http://localhost:8000" aria-label="API URL" />
          <button type="submit">Use</button>
        </form>
        <button type="button" @click="cycleTheme" :title="'theme: ' + theme">
          {{ theme === 'auto' ? '◐' : theme === 'light' ? '○' : '●' }}
        </button>
      </header>
      <main>
        <router-view></router-view>
      </main>
    </div>
  `,
};

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", component: OverviewPage },
    { path: "/asset/:symbol", component: AssetPage, props: true },
    { path: "/events", component: EventsPage },
  ],
});

createApp(Shell).use(router).mount("#app");
