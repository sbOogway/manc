// The theme: the viewer's choice (auto, light, dark) resolved against the system preference and
// stamped on <html data-theme>, which the CSS tokens and PrimeVue's dark-mode selector both read.
import { computed, ref } from "vue";

export const THEMES = ["auto", "light", "dark"] as const;
export type Theme = (typeof THEMES)[number];
export type Resolved = "light" | "dark";
const STORAGE_KEY = "manc.theme";

export function themeName(chosen: string | undefined, prefersDark: boolean): Resolved {
  return chosen === "dark" || chosen === "light" ? chosen : prefersDark ? "dark" : "light";
}

export function nextTheme(current: Theme): Theme {
  return THEMES[(THEMES.indexOf(current) + 1) % THEMES.length] ?? "auto";
}

function readChoice(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return THEMES.includes(stored as Theme) ? (stored as Theme) : "auto";
  } catch {
    return "auto";
  }
}

function systemPrefersDark(): boolean {
  return globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

const choice = ref<Theme>(readChoice());
const prefersDark = ref(systemPrefersDark());
globalThis.matchMedia?.("(prefers-color-scheme: dark)").addEventListener("change", (event) => {
  prefersDark.value = event.matches;
});
const resolved = computed<Resolved>(() => themeName(choice.value === "auto" ? undefined : choice.value, prefersDark.value));

export function useTheme() {
  function set(theme: Theme): void {
    choice.value = theme;
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // storage unavailable: the choice lasts the page
    }
  }
  function cycle(): void {
    set(nextTheme(choice.value));
  }
  return { choice, resolved, set, cycle };
}
