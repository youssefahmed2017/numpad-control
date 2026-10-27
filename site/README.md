# The NumpadPilot landing page

`index.html` is the whole site: no build step, no libraries. GitHub publishes it at
<https://youssefahmed2017.github.io/numpad-pilot/> whenever `site/` changes on `main`
(`.github/workflows/pages.yml`; enable it once under Settings → Pages → Source: GitHub Actions).

Two settings at the top of the script connect it to free accounts:

- `FORM_ENDPOINT`: where waitlist sign-ups go (a [Formspree](https://formspree.io) form URL).
- `GOATCOUNTER`: visit counting without cookies ([GoatCounter](https://www.goatcounter.com) code).

**The price test** (plan, section 8): each visitor sees $4.99 (variant `a`) or $9.99 (`b`),
kept per browser. Every sign-up records `variant` and `price_shown` with its pre-order answer,
and GoatCounter counts page views per price (`/?price=a`, `/?price=b`). Add `?price=a` or
`?price=b` to the address to see a variant yourself.
