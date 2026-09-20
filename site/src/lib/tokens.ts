// The CSS tokens as a reactive value: charts rebuild their figures when the theme flips.
import { computed, nextTick, ref, watch } from "vue";

import { type Tokens, readTokens } from "./charts";
import { useTheme } from "./theme";

const version = ref(0);
let watching = false;

export function useTokens() {
  if (!watching) {
    watching = true;
    watch(useTheme().resolved, async () => {
      await nextTick(); // the data-theme attribute lands first, then the tokens are re-read
      version.value += 1;
    });
  }
  return computed<Tokens>(() => {
    void version.value;
    return readTokens();
  });
}
