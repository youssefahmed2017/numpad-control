# The NumpadControl website

Plain HTML, CSS and JavaScript: no build step, no libraries. Vercel serves it at
<https://numpad.ahmedabdou.net/> whenever `site/`, `docs/screenshots/` or `vercel.json` change on `main` (the project is
`numpad-control-site`; `vercel.json` copies the app screenshots into the site while it builds).

## Pages

`index.html` (home, with the live numpad demo), `features.html`, `docs.html` (guides and the app screenshots), `pricing.html` ("Why free"),
`download.html`, `faq.html`, `issues.html` (the crash reports people sent, read from `/api/issues`), `privacy.html` and `404.html`.

The crash-report API lives in `../api/` (Vercel functions + a Neon database: `DATABASE_URL`; `ADMIN_TOKEN` marks issues fixed;
`RATE_SALT` salts the daily address hash). `npm test` runs its tests. Every page has the same skeleton:
an empty `<header class="appbar">` and `<footer class="site">`, which `assets/site.js` fills
with the navigation, the colour picker, the phone drawer and the footer. To add a page, copy
one, then add it to `PAGES` in `site.js`.

## Assets

The look comes from [BeerCSS](https://www.beercss.com) 5.0.3 (MIT, Material Design 3), copied into `assets/beer/` so
the site makes no calls to a CDN or to Google's font servers (the privacy page says so). Two edits were made to its CSS:
the CDN fallbacks for the icon font were removed, and the font faces the site doesn't use. `material-symbols-outlined.woff2`
there is Google's Material Symbols Outlined cut down to the icons the pages use (5 KB instead of 460 KB); to add an icon,
add its name to a page, re-cut the font from `material-symbols-outlined.woff2` in the BeerCSS package (fontTools, with the
`rlig` feature and no layout closure, FILL pinned to 0) and replace the file.

- `site.css`: what the pages need on top of BeerCSS: the live demo pad, stat tiles, code blocks, the footer.
- `palettes.js`: the light and dark colour schemes of the app's 7 accent colours, exported from the app.
- `theme.js`: applies the chosen accent and light/dark mode to BeerCSS's colour variables before the page draws (no flash),
  and remembers them in the browser. So the site and the app share their colours.
- `site.js`: header, drawer, colour dialog, footer, the demo and visit counting.
- `fonts/roboto-flex-latin.woff2`: served from this site, so no calls to Google.

## Settings

One setting at the top of `site.js` connects the site to a free account:

- `GOATCOUNTER`: visit counting without cookies ([GoatCounter](https://www.goatcounter.com) code).

GoatCounter counts page views and button clicks (`data-track`). Nothing else is collected.

## Screenshots and the video

The pictures on `docs.html` are the ones in `docs/screenshots/`. The Docs screenshots workflow redraws them from the
app's code when `numpadctl_ui/` changes, and Vercel copies them into the site while it builds (`vercel.json`,
`site/img/screenshots/`). The demo video on the home page is `video/numpad-demo.mp4` with its poster
`img/demo-poster.jpg`: a real numpad filmed on a desk, cut, with the pressed key labelled. Beside it is the vertical
(9:16) cut, `video/numpad-tiktok.mp4` with `img/tiktok-poster.jpg`, made from the same footage with the app's own design tokens.
