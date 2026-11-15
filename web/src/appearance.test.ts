import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { applyAppearance, readAppearance } from "./appearance.ts";

beforeEach(() => { window.localStorage.clear(); window.history.replaceState(null, "", "/"); });
afterEach(() => { vi.restoreAllMocks(); window.localStorage.clear(); window.history.replaceState(null, "", "/"); });

it("defaults to light and remembers an explicit dark preference", () => {
  expect(readAppearance()).toBe("light");
  applyAppearance("dark");
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(readAppearance()).toBe("dark");
});

it("lets explicit preview links override a remembered appearance", () => {
  applyAppearance("dark");
  window.history.replaceState(null, "", "/?theme=light");
  expect(readAppearance()).toBe("light");
});

it("still switches appearance when browser storage is unavailable", () => {
  vi.spyOn(window.localStorage, "getItem").mockImplementation(() => { throw new Error("Storage blocked"); });
  vi.spyOn(window.localStorage, "setItem").mockImplementation(() => { throw new Error("Storage blocked"); });
  expect(readAppearance()).toBe("light");
  expect(() => applyAppearance("dark")).not.toThrow();
  expect(document.documentElement.dataset.theme).toBe("dark");
});
