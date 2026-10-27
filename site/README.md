# The NumpadPilot website

Plain HTML, CSS and JavaScript: no build step, no libraries. GitHub publishes it at
<https://youssefahmed2017.github.io/numpad-pilot/> whenever `site/` changes on `main`
(`.github/workflows/pages.yml`; enable it once under Settings → Pages → Source: GitHub Actions).

## Pages

`index.html` (home, with the live numpad demo), `features.html`, `pricing.html`,
`download.html`, `faq.html`, `privacy.html` and `404.html`. Every page has the same skeleton:
an empty `<header class="appbar">` and `<footer class="site">`, which `assets/site.js` fills
with the navigation, the colour picker, the phone drawer and the footer. To add a page, copy
one, then add it to `PAGES` in `site.js`.

## Assets

- `style.css`: the Material 3 (Material You) design: colour roles as `--md-*` variables,
  type scale, buttons that change shape when pressed, ripples, cards, scroll reveal.
- `palettes.js`: the light and dark colour schemes of the app's 7 accent colours, exported
  from the app so the site and the app match.
- `theme.js`: applies the chosen accent and light/dark mode before the page draws (no flash),
  and remembers them in the browser.
- `site.js`: header, footer, icons, ripples, the demo, the waitlist form, the price test and
  visit counting.
- `fonts/roboto-flex-latin.woff2`: served from this site, so no calls to Google.

## Settings

Two settings at the top of `site.js` connect the site to free accounts:

- `FORM_ENDPOINT`: where waitlist sign-ups go (a [Formspree](https://formspree.io) form URL).
- `GOATCOUNTER`: visit counting without cookies ([GoatCounter](https://www.goatcounter.com) code).

**The price test** (plan, section 8): each visitor sees $4.99 (variant `a`) or $9.99 (`b`),
kept per browser. Every sign-up records `variant`, `price_shown` and `page` with its
pre-order answer, and GoatCounter counts page views per price (`/?price=a`, `/?price=b`).
Add `?price=a` or `?price=b` to the address to see a variant yourself.

To preview locally: `python -m http.server -d site` and open <http://localhost:8000>.
