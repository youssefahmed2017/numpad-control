// NumpadPilot website: everything shared by the pages (one source for the header, footer and form).
(function () {
  // ---- settings: the accounts this site reports to ----
  const FORM_ENDPOINT = "https://formspree.io/f/mgaakpzq";  // waitlist sign-ups (Formspree: "NumpadPilot waitlist")
  const GOATCOUNTER = "youssefahmedstartscodingat2017";     // visit counts: https://youssefahmedstartscodingat2017.goatcounter.com
  const GITHUB = "https://github.com/youssefahmed2017/numpad-pilot";

  const PAGES = [
    ["index.html", "Home"], ["features.html", "Features"], ["pricing.html", "Why free"],
    ["download.html", "Get started"], ["faq.html", "FAQ"],
  ];
  const here = (location.pathname.split("/").pop() || "index.html");
  const current = (href) => (href === here ? ' aria-current="page"' : "");

  // ---- icons (Material Symbols shapes), used as <svg><use href="#i-name"/></svg> ----
  const ICONS = {
    menu: "M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z",
    palette: "M12 3a9 9 0 0 0 0 18c.83 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.01-.23-.26-.38-.61-.38-.99 0-.83.67-1.5 1.5-1.5H16a5 5 0 0 0 5-5c0-4.42-4.03-8-9-8zm-5.5 9a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm3-4a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm5 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm3 4a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z",
    videocam: "M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z",
    volume: "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.47 4.47 0 0 0 2.5-4zM14 3.2v2.1a7 7 0 0 1 0 13.4v2.1a9 9 0 0 0 0-17.6z",
    launch: "M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2v7zM14 3v2h3.6l-9.8 9.8 1.4 1.4L19 6.4V10h2V3h-7z",
    bolt: "M11 21h-1l1-7H7.5c-.6 0-.6-.3-.4-.6L13 3h1l-1 7h3.5c.5 0 .6.3.4.6L11 21z",
    window: "M19 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 14H5V8h14v10z",
    gamepad: "M21.58 16.09l-1.09-7.66A4 4 0 0 0 16.53 5H7.47a4 4 0 0 0-3.96 3.43l-1.09 7.66a2.55 2.55 0 0 0 4.32 2.17L9 16h6l2.25 2.25a2.55 2.55 0 0 0 4.33-2.16zM11 11H9v2H8v-2H6v-1h2V8h1v2h2v1zm4-1a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm2 3a1 1 0 1 1 0-2 1 1 0 0 1 0 2z",
    lock: "M18 8h-1V6a5 5 0 0 0-10 0v2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2zm-6 9a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm3.1-9H8.9V6a3.1 3.1 0 0 1 6.2 0v2z",
    terminal: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 14H4V8h16v10zm-2-1h-6v-2h6v2zM7.5 17l-1.41-1.41L8.67 13l-2.59-2.59L7.5 9l4 4-4 4z",
    layers: "M11.99 18.54l-7.37-5.73L3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z",
    check: "M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z",
    download: "M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z",
    copy: "M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z",
    mail: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z",
    keyboard: "M20 5H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm-9 3h2v2h-2V8zm0 3h2v2h-2v-2zM8 8h2v2H8V8zm0 3h2v2H8v-2zM5 11h2v2H5v-2zm0-3h2v2H5V8zm11 8H8v-2h8v2zm0-3h-2v-2h2v2zm0-3h-2V8h2v2zm3 3h-2v-2h2v2zm0-3h-2V8h2v2z",
    usb: "M15 7v4h1v2h-3V5h2l-3-4-3 4h2v8H8v-2.07c.7-.37 1.2-1.08 1.2-1.93a2.2 2.2 0 0 0-4.4 0c0 .85.5 1.56 1.2 1.93V13c0 1.11.89 2 2 2h3v3.05c-.71.37-1.2 1.1-1.2 1.95a2.2 2.2 0 0 0 4.4 0c0-.85-.49-1.58-1.2-1.95V15h3c1.11 0 2-.89 2-2v-2h1V7h-4z",
    touch: "M11.71 17.99A6 6 0 0 1 6 12a6 6 0 0 1 12 0l-.01-.29-2.1-.63A4 4 0 1 0 11.08 15.9l.63 2.09zM22 12c0 .3-.01.6-.04.9l-1.97-.59c.01-.1.01-.21.01-.31a8 8 0 1 0-8 8c.1 0 .21 0 .31-.01l.59 1.97c-.3.03-.6.04-.9.04-5.52 0-10-4.48-10-10S6.48 2 12 2s10 4.48 10 10zm-3.77 4.26L22 15l-10-3 3 10 1.26-3.77 4.27 4.27 1.98-1.98-4.28-4.26z",
    sync: "M12 4V1L8 5l4 4V6a6 6 0 0 1 5.3 8.8l1.46 1.46A7.93 7.93 0 0 0 20 12a8 8 0 0 0-8-8zm0 14a6 6 0 0 1-5.3-8.8L5.24 7.74A7.93 7.93 0 0 0 4 12a8 8 0 0 0 8 8v3l4-4-4-4v3z",
    shield: "M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z",
    timer: "M15 1H9v2h6V1zm-4 13h2V8h-2v6zm8.03-6.61 1.42-1.42c-.43-.51-.9-.99-1.41-1.41l-1.42 1.42A9 9 0 1 0 19.03 7.39zM12 20a7 7 0 1 1 0-14 7 7 0 0 1 0 14z",
    crop: "M17 15h2V7a2 2 0 0 0-2-2H9v2h8v8zM7 17V1H5v4H1v2h4v10a2 2 0 0 0 2 2h10v4h2v-4h4v-2H7z",
    bell: "M12 22c1.1 0 2-.9 2-2h-4a2 2 0 0 0 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4a1.5 1.5 0 0 0-3 0v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z",
    desktop: "M20 3H4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h6v2H8v2h8v-2h-2v-2h6a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm0 13H4V5h16v11z",
    mic: "M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z",
    sparkle: "M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z",
    code: "M9.4 16.6 4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0 4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z",
    arrow: "M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z",
    money: "M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z",
    globe: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.93 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.99 7.99 0 0 1 5.08 16zm2.95-8H5.08a7.99 7.99 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z",
  };
  const sprite = '<svg width="0" height="0" style="position:absolute" aria-hidden="true">' +
    Object.entries(ICONS).map(([k, d]) => `<symbol id="i-${k}" viewBox="0 0 24 24"><path fill="currentColor" d="${d}"/></symbol>`).join("") + "</svg>";
  const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;

  const LOGO = `<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="4" y="4" width="56" height="56" rx="18" fill="var(--md-primary)"/>
    <g fill="var(--md-onPrimary)"><rect x="15" y="15" width="10" height="10" rx="3.5"/><rect x="27" y="15" width="10" height="10" rx="3.5"/>
    <rect x="39" y="15" width="10" height="10" rx="3.5"/><rect x="15" y="27" width="10" height="10" rx="3.5"/><rect x="27" y="27" width="10" height="10" rx="3.5"/>
    <rect x="39" y="27" width="10" height="22" rx="3.5"/><rect x="15" y="39" width="22" height="10" rx="3.5"/></g></svg>`;

  // ---- header, drawer, footer ----
  function buildChrome() {
    document.body.insertAdjacentHTML("afterbegin", sprite);
    const header = document.querySelector("header.appbar");
    header.innerHTML = `
      <div class="wrap">
        <button class="icon-btn menu-btn" id="menu" aria-label="Open the menu">${icon("menu")}</button>
        <a class="brand" href="index.html">${LOGO}NumpadPilot</a>
        <nav class="nav" aria-label="Pages">${PAGES.map(([h, t]) => `<a href="${h}"${current(h)}>${t}</a>`).join("")}</nav>
        <button class="icon-btn" id="theme" aria-label="Colours and dark mode" aria-expanded="false">${icon("palette")}</button>
        <a class="btn filled small" href="index.html#waitlist" data-track="nav-waitlist">Join the waitlist</a>
      </div>
      <div class="picker" id="picker" role="dialog" aria-label="Colours">
        <h3>Pick your colour</h3>
        <div class="swatches">${Object.entries(NumpadTheme.seeds).map(([name, hex]) =>
          `<button class="swatch" style="background:${hex}" data-accent="${name}" aria-label="${name}" title="${name}"></button>`).join("")}</div>
        <h3 style="margin-top:18px">Appearance</h3>
        <div class="modes">${["auto", "light", "dark"].map(m =>
          `<button data-mode="${m}">${m === "auto" ? "System" : m[0].toUpperCase() + m.slice(1)}</button>`).join("")}</div>
        <p class="muted" style="font-size:13px;margin:14px 0 0">Material You: the whole site re-tints from one colour, like the app.</p>
      </div>`;
    document.body.insertAdjacentHTML("beforeend", `
      <div class="drawer-scrim" id="scrim"></div>
      <nav class="drawer" aria-label="Pages">
        <a class="brand" href="index.html" style="padding:6px 16px 18px">${LOGO}NumpadPilot</a>
        ${PAGES.map(([h, t]) => `<a href="${h}"${current(h)}>${t}</a>`).join("")}
        <a href="privacy.html"${current("privacy.html")}>Privacy</a>
        <a href="${GITHUB}">GitHub</a>
      </nav>
      <a class="fab" href="index.html#waitlist" data-track="fab-waitlist">${icon("mail")}Join the waitlist</a>`);
    const footer = document.querySelector("footer.site");
    footer.innerHTML = `
      <div class="wrap">
        <div class="cols">
          <div><a class="brand" href="index.html">${LOGO}NumpadPilot</a>
            <p class="muted" style="max-width:360px">Turn any cheap USB numpad into a control deck. Windows and Linux, no driver, no telemetry.</p></div>
          <div><h4>Product</h4><a href="features.html">Features</a><a href="pricing.html">Why free</a><a href="download.html">Get started</a></div>
          <div><h4>Help</h4><a href="faq.html">FAQ</a><a href="${GITHUB}/blob/main/docs/compatibility.md">Tested numpads</a><a href="${GITHUB}/issues">Report a problem</a></div>
          <div><h4>Open source</h4><a href="${GITHUB}">GitHub</a><a href="privacy.html">Privacy</a><a href="${GITHUB}/blob/main/LICENSE">GPL-3.0</a></div>
        </div>
        <p class="fine">Stream Deck is a trademark of Corsair / Elgato; NumpadPilot isn't affiliated with them.
          This site counts visits without cookies and keeps nothing about you.</p>
      </div>`;
  }

  function wireChrome() {
    const header = document.querySelector("header.appbar");
    const onScroll = () => {
      header.classList.toggle("scrolled", scrollY > 8);
      const fab = document.querySelector(".fab");
      const target = document.getElementById("waitlist");
      if (fab && target) {
        const r = target.getBoundingClientRect();
        fab.classList.toggle("hidden", r.top < innerHeight && r.bottom > 0);
      }
    };
    addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    const picker = document.getElementById("picker"), themeBtn = document.getElementById("theme");
    const syncPicker = () => {
      picker.querySelectorAll(".swatch").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.accent === NumpadTheme.accent)));
      picker.querySelectorAll("[data-mode]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === NumpadTheme.mode)));
    };
    syncPicker();
    document.addEventListener("themechange", syncPicker);
    themeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = picker.classList.toggle("open");
      themeBtn.setAttribute("aria-expanded", String(open));
    });
    picker.addEventListener("click", (e) => {
      e.stopPropagation();
      const swatch = e.target.closest("[data-accent]"), mode = e.target.closest("[data-mode]");
      if (swatch) { NumpadTheme.set({ accent: swatch.dataset.accent }); count("theme-" + swatch.dataset.accent); }
      if (mode) NumpadTheme.set({ mode: mode.dataset.mode });
    });
    document.addEventListener("click", () => { picker.classList.remove("open"); themeBtn.setAttribute("aria-expanded", "false"); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { picker.classList.remove("open"); document.body.classList.remove("drawer-open"); }
    });

    document.getElementById("menu").addEventListener("click", () => document.body.classList.add("drawer-open"));
    document.getElementById("scrim").addEventListener("click", () => document.body.classList.remove("drawer-open"));
  }

  // ---- ripples on everything pressable ----
  function wireRipples() {
    document.addEventListener("pointerdown", (e) => {
      const host = e.target.closest(".btn, .icon-btn, .nav a, .drawer a, .key, .fab, .modes button, .os-tabs button, .segmented label, a.card");
      if (!host) return;
      const r = host.getBoundingClientRect();
      const size = Math.max(r.width, r.height) * 2.2;
      const dot = document.createElement("span");
      dot.className = "ripple";
      dot.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - r.left - size / 2}px;top:${e.clientY - r.top - size / 2}px`;
      host.appendChild(dot);
      dot.addEventListener("animationend", () => dot.remove());
    });
  }

  // ---- scroll reveal (children of [data-stagger] come in one after another) ----
  function wireReveal() {
    document.querySelectorAll("[data-stagger]").forEach(group =>
      [...group.children].forEach((child, i) => { child.classList.add("reveal"); child.style.transitionDelay = `${Math.min(i, 8) * 70}ms`; }));
    // Everything at or above the bottom of the screen shows, so sections skipped by a fast
    // scroll or an #anchor jump don't stay invisible (an IntersectionObserver misses those).
    let pending = [...document.querySelectorAll(".reveal")], queued = false;
    const check = () => {
      queued = false;
      const fold = innerHeight - 40;
      pending = pending.filter(el => {
        if (el.getBoundingClientRect().top > fold) return true;
        el.classList.add("in");
        return false;
      });
      if (!pending.length) { removeEventListener("scroll", onScroll); removeEventListener("resize", onScroll); }
    };
    const onScroll = () => { if (!queued) { queued = true; requestAnimationFrame(check); } };
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("resize", onScroll);
    check();
  }

  // ---- the live numpad on the home page ----
  const KEYS = [
    ["Num", "Do not disturb", "Do not disturb", "Notifications off", "bell"], ["/", "Screenshot", "Screenshot: region", "Copied to the clipboard", "crop"],
    ["*", "Mic mute", "Microphone mute", "Mic muted", "mic"], ["⌫", "Undo", "Press keys: Ctrl+Z", "Undone", "keyboard"],
    ["7", "Live macro", "Macro: scene → wait 3 s → go live", "Live!", "bolt"], ["8", "Scene: Chat", "OBS: switch scene", "Scene: Just chatting", "videocam"],
    ["9", "Spotify +", "App volume up", "Spotify 70%", "volume"], ["-", "Volume −", "Volume down", "Volume 40%", "volume"],
    ["4", "Scene: Game", "OBS: switch scene", "Scene: Gameplay", "videocam"], ["5", "Record", "OBS: start recording (hold: stop)", "Recording", "videocam"],
    ["6", "Mute desktop", "OBS: mute an audio source", "Desktop audio muted", "volume"], ["+", "Volume +", "Volume up", "Volume 60%", "volume"],
    ["1", "Browser", "Open the default browser", "Opening your browser", "launch"], ["2", "Editor", "Launch an app", "Opening DaVinci Resolve", "launch"],
    ["3", "Discord", "Focus a window", "Discord in front", "window"], ["⏎", "Layer", "Layer key: hold for 19 more actions", "Layer 2", "layers", "tall"],
    ["0", "Play/pause", "Media: play / pause", "Paused", "volume"], ["000", "Replay", "OBS: save the replay buffer", "Replay saved", "videocam"],
    [".", "Lock", "Lock the screen", "Locked", "lock"],
  ];
  function wireDemo() {
    const pad = document.getElementById("pad");
    if (!pad) return;
    pad.innerHTML = KEYS.map(([label, short, , , , tall], i) =>
      `<button class="key${tall ? " tall" : ""}" data-i="${i}" aria-label="${label}: ${short}">${label}<small>${short}</small></button>`).join("");
    // grid placement like a real numpad: Enter spans two rows, 0 is wide on real pads but 000 sits next to it here
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
    pad.addEventListener("click", (e) => { const k = e.target.closest(".key"); if (k) press(+k.dataset.i, true); });
    const sequence = [9, 8, 17, 11, 4, 12, 0, 7];
    let step = 0;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduced) setInterval(() => { if (auto && !document.hidden) press(sequence[step++ % sequence.length], false); }, 2300);
    setTimeout(() => press(9, false), 900);
  }

  // ---- download page: OS tabs and copy buttons ----
  function wireDownload() {
    document.querySelectorAll(".os-tabs").forEach(tabs => tabs.addEventListener("click", (e) => {
      const tab = e.target.closest("button[data-os]");
      if (!tab) return;
      tabs.querySelectorAll("button").forEach(b => b.setAttribute("aria-selected", String(b === tab)));
      document.querySelectorAll(".os-panel").forEach(p => { p.hidden = p.dataset.os !== tab.dataset.os; });
    }));
    const isLinux = /Linux/.test(navigator.userAgent) && !/Android/.test(navigator.userAgent);
    const start = document.querySelector(`.os-tabs button[data-os="${isLinux ? "linux" : "windows"}"]`);
    if (start) start.click();
    document.querySelectorAll(".code").forEach(block => {
      const button = document.createElement("button");
      button.className = "icon-btn copy";
      button.setAttribute("aria-label", "Copy");
      button.innerHTML = icon("copy");
      button.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(block.dataset.copy || block.textContent.trim()); button.innerHTML = icon("check"); }
        catch (e) { /* no clipboard: the text can still be selected */ }
        setTimeout(() => { button.innerHTML = icon("copy"); }, 1600);
      });
      block.appendChild(button);
    });
  }

  // ---- the waitlist form (on every page that has <div data-waitlist>) ----
  function waitlistHTML(id) {
    return `
      <form class="signup reveal" id="${id}" novalidate>
        <span class="badge">Free · open source · beta</span>
        <h2 class="headline" style="margin-top:14px">Join the waitlist</h2>
        <p class="muted" style="margin:0">Get an email when the one-click installer and big updates are out. Nothing else, ever.</p>
        <div class="field"><input id="${id}-email" name="email" type="email" required placeholder=" " autocomplete="email"><label for="${id}-email">Your email</label></div>
        <div class="field"><select id="${id}-use" name="use">
          <option value="streaming">Streaming (OBS, Twitch, YouTube…)</option><option value="editing">Video or photo editing</option>
          <option value="gaming">Gaming</option><option value="work">Work and productivity</option><option value="other">Something else</option>
        </select><label for="${id}-use">What would you use it for?</label></div>
        <p class="question">Which computer is it for? <span class="muted">(optional)</span></p>
        <div class="segmented" role="radiogroup">
          <label><input type="radio" name="os" value="windows">Windows</label>
          <label><input type="radio" name="os" value="linux">Linux</label>
          <label><input type="radio" name="os" value="mac">Mac</label>
        </div>
        <input type="hidden" name="page" value="${here}">
        <p style="margin:26px 0 0"><button class="btn filled" type="submit">${icon("mail")}Join the waitlist</button></p>
        <div class="form-done">${icon("check")}<span>You're on the list. We'll email you when there's news.</span></div>
        <p class="form-note">Only used for NumpadPilot news. No spam; unsubscribe any time. <a href="privacy.html">Privacy</a></p>
      </form>`;
  }
  function wireWaitlist() {
    document.querySelectorAll("[data-waitlist]").forEach((slot, n) => { slot.innerHTML = waitlistHTML("waitlist-form-" + n); });
    document.querySelectorAll("form.signup").forEach(form => form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const note = form.querySelector(".form-note");
      const email = form.querySelector('input[type="email"]');
      if (!email.value || !email.checkValidity()) { email.focus(); note.textContent = "Please enter a valid email address."; return; }
      const button = form.querySelector('button[type="submit"]');
      const answers = new FormData(form);  // read before disabling: disabled fields aren't sent
      button.disabled = true;
      try {
        const response = await fetch(FORM_ENDPOINT, { method: "POST", body: answers, headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error(response.status);
        form.querySelectorAll("input, select, button").forEach(el => { el.disabled = true; });
        form.querySelector(".form-done").classList.add("show");
        note.textContent = "Thanks! Tell a streamer friend 🙂";
        count("signup-" + (answers.get("os") || "unknown"));
      } catch (e) {
        button.disabled = false;
        note.textContent = "That didn't go through. Please try again in a moment.";
      }
    }));
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
    wireWaitlist();
    document.querySelectorAll("[data-icon]").forEach(el => { el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon)); });
    wireChrome();
    wireRipples();
    wireDemo();
    wireDownload();
    wireReveal();
    wireCounting();
  });
})();
