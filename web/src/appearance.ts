export type Appearance = "light" | "dark";
const KEY = "sarstellar-appearance";

/** New visitors get light; explicit preview links take priority over a saved preference. */
export function readAppearance(): Appearance {
  const requested = new URLSearchParams(window.location.search).get("theme");
  if (requested === "light" || requested === "dark") return requested;
  try {
    return window.localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyAppearance(appearance: Appearance): void {
  document.documentElement.dataset.theme = appearance;
  try {
    window.localStorage.setItem(KEY, appearance);
  } catch {
    // Private or restricted storage must not prevent using either appearance.
  }
}
