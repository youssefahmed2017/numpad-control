// Material You colour engine: applies the chosen accent (and light/dark) before the page paints.
// Runs in <head>, right after palettes.js, so there's no flash of the wrong colours.
(function () {
  const store = {
    get(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode: fine */ } },
  };
  const P = window.M3_PALETTES;
  const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

  function scheme(mode) {
    return mode === "auto" ? (darkQuery.matches ? "dark" : "light") : mode;
  }

  function apply(accent, mode, animate) {
    if (!P) return;
    if (!P.seeds[accent]) accent = "Orchid";
    const s = scheme(mode);
    const root = document.documentElement;
    if (animate) {
      root.classList.add("tinting");
      clearTimeout(apply.timer);
      apply.timer = setTimeout(() => root.classList.remove("tinting"), 700);
    }
    for (const [role, value] of Object.entries(P[s][accent])) root.style.setProperty("--md-" + role, value);
    root.dataset.scheme = s;
    root.dataset.accent = accent;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = P[s][accent].surface;
  }

  const theme = {
    accent: store.get("np-accent", "Orchid"),
    mode: store.get("np-mode", "auto"),
    seeds: P ? P.seeds : {},
    set(changes) {
      Object.assign(theme, changes);
      store.set("np-accent", theme.accent);
      store.set("np-mode", theme.mode);
      apply(theme.accent, theme.mode, true);
      document.dispatchEvent(new CustomEvent("themechange"));
    },
  };
  window.NumpadTheme = theme;
  apply(theme.accent, theme.mode, false);
  darkQuery.addEventListener("change", () => { if (theme.mode === "auto") apply(theme.accent, theme.mode, true); });
})();
