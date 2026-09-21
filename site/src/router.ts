import { createRouter, createWebHashHistory } from "vue-router";

import AssetPage from "./pages/AssetPage.vue";
import EventsPage from "./pages/EventsPage.vue";
import OverviewPage from "./pages/OverviewPage.vue";

// Hash history: one index.html serves every route, wherever the build is mounted.
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", component: OverviewPage },
    { path: "/asset/:symbol", component: AssetPage, props: true },
    { path: "/events", component: EventsPage },
  ],
});
