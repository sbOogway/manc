<script setup lang="ts">
import Button from "primevue/button";
import { ref, watchEffect } from "vue";

import { useClient } from "./lib/client";
import { formatDate } from "./lib/format";
import { useTheme } from "./lib/theme";

const client = useClient();
const theme = useTheme();
const health = ref<{ state: "checking" | "ok" | "down"; text: string }>({ state: "checking", text: "checking…" });

watchEffect(() => {
  document.documentElement.dataset.theme = theme.resolved.value;
});

async function check(): Promise<void> {
  health.value = { state: "checking", text: "checking…" };
  try {
    const answer = await client.health();
    health.value = { state: "ok", text: answer.last_run ? `last run ${formatDate(answer.last_run)}` : "no run yet" };
  } catch (error) {
    health.value = { state: "down", text: (error as Error).message };
  }
}

const THEME_GLYPH = { auto: "◐", light: "○", dark: "●" } as const;
check();
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink class="brand" to="/">manc</RouterLink>
      <nav class="nav">
        <RouterLink to="/">Overview</RouterLink>
        <RouterLink to="/events">Events</RouterLink>
      </nav>
      <span class="spacer"></span>
      <span class="backend">
        <span class="status-dot" :class="health.state" :title="health.text"></span>
        <span class="ink-2">{{ health.text }}</span>
      </span>
      <Button
        type="button"
        size="small"
        severity="secondary"
        outlined
        :label="THEME_GLYPH[theme.choice.value]"
        :title="'theme: ' + theme.choice.value"
        @click="theme.cycle()"
      />
    </header>
    <main>
      <RouterView />
    </main>
    <footer class="credits muted small">
      Scores by manc · on-chain data by Coin Metrics Community (CC BY-NC 4.0), DefiLlama and the Solana RPC · prices by TradingView
    </footer>
  </div>
</template>
