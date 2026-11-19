// Colour engine: applies the chosen accent (and light/dark) to BeerCSS's colour variables before the page paints.
// The schemes are the app's own (palettes.js, made with Google's Material color utilities from each seed colour),
// so the website and the settings window match. Runs in <head>, right after palettes.js: no flash of wrong colours.
(function () {
  const store = {
    get(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode: fine */ } },
  };
  const P = window.M3_PALETTES;
  const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const kebab = (s) => s.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());
  const ERROR = {
    light: { error: "#ba1a1a", onError: "#ffffff", errorContainer: "#ffdad6", onErrorContainer: "#410002" },
    dark: { error: "#ffb4ab", onError: "#690005", errorContainer: "#93000a", onErrorContainer: "#ffdad6" },
  };
  const style = document.createElement("style");
  style.id = "np-colours";
  document.head.appendChild(style);

  function scheme(mode) {
    return mode === "auto" ? (darkQuery.matches ? "dark" : "light") : mode;
  }

  function apply(accent, mode, animate) {
    if (!P) return;
    if (!P.seeds[accent]) accent = "Orchid";
    const s = scheme(mode);
    const roles = Object.assign({}, P[s][accent], ERROR[s]);
    roles.background = roles.surface;
    roles.onBackground = roles.onSurface;
    roles.surfaceVariant = roles.surfaceContainerHighest;
    roles.shadow = "#000000";
    roles.scrim = "#000000";
    // body.light / body.dark carry BeerCSS's own colours: these rules have the same weight and come later, so they win
    const css = Object.entries(roles).map(([role, value]) => `--${kebab(role)}:${value};`).join("");
    style.textContent = `:root,body,body.light,body.dark{${css}color-scheme:${s};}`;
    const root = document.documentElement;
    root.dataset.scheme = s;
    root.dataset.accent = accent;
    if (animate) {
      root.classList.add("tinting");
      clearTimeout(apply.timer);
      apply.timer = setTimeout(() => root.classList.remove("tinting"), 600);
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = roles.surface;
    if (document.body) document.body.classList.remove("light", "dark"), document.body.classList.add(s);
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
  document.addEventListener("DOMContentLoaded", () => apply(theme.accent, theme.mode, false));
  darkQuery.addEventListener("change", () => { if (theme.mode === "auto") apply(theme.accent, theme.mode, true); });
})();
