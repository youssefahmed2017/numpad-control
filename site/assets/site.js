// NumpadControl website: everything shared by the pages (one source for the header, footer, colour picker and demo).
(function () {
  // ---- settings: the accounts this site reports to ----
  const GOATCOUNTER = "youssefahmedstartscodingat2017";     // visit counts: https://youssefahmedstartscodingat2017.goatcounter.com
  const GITHUB = "https://github.com/youssefahmed2017/numpad-control";
  const KOFI = "https://ko-fi.com/youssefahmedabdou";  // the optional tip jar

  const PAGES = [
    ["index.html", "Home"], ["features.html", "Features"], ["pricing.html", "Why free"],
    ["download.html", "Get started"], ["docs.html", "Docs"], ["faq.html", "FAQ"],
    ["issues.html", "Issues"],
  ];
  const here = (location.pathname.split("/").pop() || "index.html");
  const icon = (name) => `<i aria-hidden="true">${name}</i>`;

  const LOGO = `<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="4" y="4" width="56" height="56" rx="18" fill="var(--primary)"/>
    <g fill="var(--on-primary)"><rect x="15" y="15" width="10" height="10" rx="3.5"/><rect x="27" y="15" width="10" height="10" rx="3.5"/>
    <rect x="39" y="15" width="10" height="10" rx="3.5"/><rect x="15" y="27" width="10" height="10" rx="3.5"/><rect x="27" y="27" width="10" height="10" rx="3.5"/>
    <rect x="39" y="27" width="10" height="22" rx="3.5"/><rect x="15" y="39" width="22" height="10" rx="3.5"/></g></svg>`;

  // ---- header, drawer, colour dialog, footer ----
  function buildChrome() {
    const links = PAGES.map(([h, t]) =>
      `<a class="button round ${h === here ? "secondary-container" : "transparent"}" href="${h}"${h === here ? ' aria-current="page"' : ""}>${t}</a>`).join("");
    document.querySelector("header.np-bar").innerHTML = `
      <nav>
        <button class="circle transparent s" data-ui="#np-drawer" aria-label="Open the menu">${icon("menu")}</button>
        <a class="np-brand" href="index.html">${LOGO}NumpadControl</a>
        <div class="max"></div>
        <div class="m l">${links}</div>
        <button class="circle transparent" data-ui="#np-colours" aria-label="Colours and dark mode">${icon("palette")}</button>
        <a class="button round" href="download.html#install" data-track="nav-install">${icon("download")}<span>Install</span></a>
      </nav>`;
    document.body.insertAdjacentHTML("beforeend", `
      <dialog class="left" id="np-drawer">
        <nav class="drawer">
          <header><nav><a class="np-brand" href="index.html">${LOGO}NumpadControl</a><div class="max"></div>
            <button class="circle transparent" data-ui="#np-drawer" aria-label="Close">${icon("close")}</button></nav></header>
          ${PAGES.map(([h, t]) => `<a href="${h}"${h === here ? ' class="active"' : ""}><span>${t}</span></a>`).join("")}
          <a href="privacy.html"><span>Privacy</span></a>
          <a href="${GITHUB}"><span>GitHub</span></a>
        </nav>
      </dialog>
      <dialog id="np-colours" class="round">
        <h5>Pick your colour</h5>
        <div class="np-swatches">${Object.entries(NumpadTheme.seeds).map(([name, hex]) =>
          `<button class="np-swatch" style="background:${hex}" data-accent="${name}" aria-label="${name}" title="${name}" aria-pressed="false"></button>`).join("")}</div>
        <h6>Appearance</h6>
        <div class="row" role="group">${["auto", "light", "dark"].map(m =>
          `<button class="chip" data-mode="${m}" aria-pressed="false">${m === "auto" ? "System" : m[0].toUpperCase() + m.slice(1)}</button>`).join("")}</div>
        <p class="small-text">The whole site re-tints from one colour, like the app does.</p>
        <nav class="right-align"><button class="transparent link" data-ui="#np-colours">Close</button></nav>
      </dialog>`);
    document.querySelector("footer.np-foot").innerHTML = `
      <div class="np-cols">
        <div><a class="np-brand" href="index.html">${LOGO}NumpadControl</a>
          <p style="max-width:360px;color:var(--on-surface-variant)">Turn any cheap USB numpad into a control deck. Windows and Linux, no driver, no telemetry.</p></div>
        <div><h6>Product</h6><a href="features.html">Features</a><a href="pricing.html">Why free</a><a href="download.html">Get started</a><a href="docs.html">Docs</a><a href="roadmap.html">Roadmap</a></div>
        <div><h6>Help</h6><a href="faq.html">FAQ</a><a href="${GITHUB}/blob/main/docs/compatibility.md">Tested numpads</a><a href="issues.html">Report a problem</a><a href="${GITHUB}/blob/main/CHANGELOG.md">Changelog</a></div>
        <div><h6>Open source</h6><a href="${GITHUB}">GitHub</a><a href="privacy.html">Privacy</a><a href="code-signing.html">Code signing policy</a><a href="${GITHUB}/blob/main/LICENSE">GPL-3.0</a><a href="${KOFI}">Leave a tip</a></div>
      </div>
      <p class="np-fine">Stream Deck is a trademark of Corsair / Elgato; NumpadControl isn't affiliated with them.
        This site counts visits without cookies and keeps nothing about you. Built with <a style="display:inline" href="https://www.beercss.com">BeerCSS</a>.</p>`;
  }

  function wireChrome() {
    const dialog = document.getElementById("np-colours");
    const sync = () => {
      dialog.querySelectorAll("[data-accent]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.accent === NumpadTheme.accent)));
      dialog.querySelectorAll("[data-mode]").forEach(b => {
        const on = b.dataset.mode === NumpadTheme.mode;
        b.setAttribute("aria-pressed", String(on));
        b.classList.toggle("fill", on);
      });
    };
    sync();
    document.addEventListener("themechange", sync);
    dialog.addEventListener("click", (e) => {
      const swatch = e.target.closest("[data-accent]"), mode = e.target.closest("[data-mode]");
      if (swatch) { NumpadTheme.set({ accent: swatch.dataset.accent }); count("theme-" + swatch.dataset.accent); }
      if (mode) NumpadTheme.set({ mode: mode.dataset.mode });
    });
  }

  // ---- the live numpad on the home page ----
  const KEYS = [
    ["Num", "Do not disturb", "Do not disturb", "Notifications off", "notifications_off"], ["/", "Screenshot", "Screenshot: region", "Copied to the clipboard", "crop"],
    ["*", "Mic mute", "Microphone mute", "Mic muted", "mic_off"], ["⌫", "Undo", "Press keys: Ctrl+Z", "Undone", "keyboard"],
    ["7", "Live macro", "Macro: scene → wait 3 s → go live", "Live!", "bolt"], ["8", "Scene: Chat", "OBS: switch scene", "Scene: Just chatting", "videocam"],
    ["9", "Spotify +", "App volume up", "Spotify 70%", "volume_up"], ["-", "Volume −", "Volume down", "Volume 40%", "volume_down"],
    ["4", "Scene: Game", "OBS: switch scene", "Scene: Gameplay", "videocam"], ["5", "Record", "OBS: start recording (hold: stop)", "Recording", "videocam"],
    ["6", "Mute desktop", "OBS: mute an audio source", "Desktop audio muted", "volume_off"], ["+", "Volume +", "Volume up", "Volume 60%", "volume_up"],
    ["1", "Browser", "Open the default browser", "Opening your browser", "open_in_new"], ["2", "Editor", "Launch an app", "Opening DaVinci Resolve", "open_in_new"],
    ["3", "Discord", "Focus a window", "Discord in front", "web_asset"], ["⏎", "Layer", "Layer key: hold for 19 more actions", "Layer 2", "layers", "tall"],
    ["0", "Play/pause", "Media: play / pause", "Paused", "play_arrow"], ["000", "Replay", "OBS: save the replay buffer", "Replay saved", "replay"],
    [".", "Lock", "Lock the screen", "Locked", "lock"],
  ];
  function wireDemo() {
    const pad = document.getElementById("pad");
    if (!pad) return;
    pad.innerHTML = KEYS.map(([label, short, , , , tall], i) =>
      `<button class="np-key${tall ? " tall" : ""}" data-i="${i}" aria-label="${label}: ${short}">${label}<small>${short}</small></button>`).join("");
    const what = document.getElementById("demo-what"), how = document.getElementById("demo-how");
    const toast = document.getElementById("demo-toast"), toastText = document.getElementById("demo-toast-text");
    let hideTimer, auto = true, autoTimer;
    function press(i, fromUser) {
      const [label, , action, result, iconName] = KEYS[i];
      const key = pad.children[i];
      key.classList.add("down");
      setTimeout(() => key.classList.remove("down"), 260);
      what.textContent = `Key ${label}`;
      how.textContent = action;
      document.getElementById("demo-icon").innerHTML = icon(iconName);
      toastText.textContent = result;
      toast.classList.add("show");
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => toast.classList.remove("show"), 1500);
      if (fromUser) {
        auto = false;
        clearTimeout(autoTimer);
        autoTimer = setTimeout(() => { auto = true; }, 8000);
        count("demo-key-" + label);
      }
    }
    pad.addEventListener("click", (e) => { const k = e.target.closest(".np-key"); if (k) press(+k.dataset.i, true); });
    const sequence = [9, 8, 17, 11, 4, 12, 0, 7];
    let step = 0;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduced) setInterval(() => { if (auto && !document.hidden) press(sequence[step++ % sequence.length], false); }, 2300);
    setTimeout(() => press(9, false), 900);
  }

  // ---- download page: OS tabs and copy buttons ----
  function wireDownload() {
    document.querySelectorAll(".np-os-tabs").forEach(tabs => tabs.addEventListener("click", (e) => {
      const tab = e.target.closest("a[data-os]");
      if (!tab) return;
      e.preventDefault();
      tabs.querySelectorAll("a").forEach(a => a.classList.toggle("active", a === tab));
      document.querySelectorAll(".np-os-panel").forEach(p => { p.hidden = p.dataset.os !== tab.dataset.os; });
    }));
    const isLinux = /Linux/.test(navigator.userAgent) && !/Android/.test(navigator.userAgent);
    const start = document.querySelector(`.np-os-tabs a[data-os="${isLinux ? "linux" : "windows"}"]`);
    if (start) start.click();
    document.querySelectorAll(".np-code").forEach(block => {
      const button = document.createElement("button");
      button.className = "circle transparent";
      button.setAttribute("aria-label", "Copy");
      button.innerHTML = icon("content_copy");
      button.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(block.dataset.copy || block.textContent.trim()); button.innerHTML = icon("check"); }
        catch (e) { /* no clipboard: the text can still be selected */ }
        setTimeout(() => { button.innerHTML = icon("content_copy"); }, 1600);
      });
      block.appendChild(button);
    });
  }

  // ---- visit counts: GoatCounter (no cookies) ----
  function count(path) {
    if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path, title: path, event: true });
  }
  function wireCounting() {
    if (!GOATCOUNTER) return;
    window.goatcounter = { no_onload: true };
    const s = document.createElement("script");
    s.async = true;
    s.src = "https://gc.zgo.at/count.js";
    s.dataset.goatcounter = `https://${GOATCOUNTER}.goatcounter.com/count`;
    s.onload = () => window.goatcounter.count({ path: location.pathname });
    document.head.appendChild(s);
    document.addEventListener("click", (e) => {
      const tracked = e.target.closest("[data-track]");
      if (tracked) count("click-" + tracked.dataset.track);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    buildChrome();
    document.querySelectorAll("[data-icon]").forEach(el => { el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon)); });
    wireChrome();
    wireDemo();
    wireDownload();
    wireCounting();
  });
})();
