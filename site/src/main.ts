import "temporal-polyfill/global";
import { definePreset } from "@primeuix/themes";
import Aura from "@primeuix/themes/aura";
import PrimeVue from "primevue/config";
import Tooltip from "primevue/tooltip";
import { createApp } from "vue";

import App from "./App.vue";
import { createClient } from "./api/client";
import { router } from "./router";
import "./style.css";

// PrimeVue's components follow the same blue accent as the charts; dark mode follows the
// data-theme attribute the theme store stamps on <html>.
const preset = definePreset(Aura, {
  semantic: {
    primary: {
      50: "{blue.50}",
      100: "{blue.100}",
      200: "{blue.200}",
      300: "{blue.300}",
      400: "{blue.400}",
      500: "{blue.500}",
      600: "{blue.600}",
      700: "{blue.700}",
      800: "{blue.800}",
      900: "{blue.900}",
      950: "{blue.950}",
    },
  },
});

createApp(App)
  .use(router)
  .use(PrimeVue, { theme: { preset, options: { darkModeSelector: '[data-theme="dark"]' } } })
  .directive("tooltip", Tooltip)
  .provide("client", createClient())
  .mount("#app");
