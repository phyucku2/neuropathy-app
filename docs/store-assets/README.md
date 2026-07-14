# Play Store visual assets

Generated, versioned visual assets for the Play listing and the Android app.
Everything in this directory (and the Android `res/` PNGs) is produced by two
deterministic scripts — regenerate rather than hand-edit.

> **Branding note:** the icon/mark here is a generated **baseline** — a circled
> dot-with-orbit "signal/tracking" glyph derived from the app's ◍ wordmark
> aesthetic, white on the brand navy→sky gradient
> (`frontend/src/styles/tokens.css`: `--color-brand-navy-deep #0f2a45` →
> `--color-brand-blue-bright #2e86c8`). The owner may replace it with
> commissioned branding at any time; keep the filenames/paths and dimensions
> identical and nothing else needs to change. Per CLAUDE.md/ADR-0002, it must
> never reproduce the BioMech logo/wordmark. The "Neuropathy" wordmark on the
> feature graphic is the placeholder app name.

## What's here and which Play slot it fills

| File | Play Console slot | Required dimensions |
|---|---|---|
| `icon-512.png` | Store listing → App icon | 512×512 PNG, ≤1 MB, full-bleed square (Play applies its own corner mask) |
| `feature-graphic-1024x500.png` | Store listing → Feature graphic | 1024×500 PNG/JPG |
| `screenshots/01-home-improving.png` | Phone screenshots (slot 1) | 1080×2400 PNG (Play accepts 320–3840 px, 16:9–2:1) |
| `screenshots/02-trends-chart.png` | Phone screenshots (slot 2) | 1080×2400 PNG |
| `screenshots/03-check-in.png` | Phone screenshots (slot 3) | 1080×2400 PNG |
| `screenshots/04-sources.png` | Phone screenshots (slot 4) | 1080×2400 PNG |
| `screenshots/05-clinician-trend-table.png` | Phone screenshots (slot 5) | 1080×2400 PNG |

Play requires **at least 4** phone screenshots; five are provided (Home with an
improving trajectory, Trends chart, daily Check-in, Sources, and the clinician
trend table).

The same icon script also regenerates the in-app Android artwork (exact
existing filenames/paths — no manifest or Gradle change needed):

- `frontend/android/app/src/main/res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher.png` — legacy launcher (48/72/96/144/192 px)
- `.../mipmap-*/ic_launcher_round.png` — legacy round launcher (same sizes)
- `.../mipmap-*/ic_launcher_foreground.png` — adaptive-icon foreground layer (108/162/216/324/432 px). The gradient is full-bleed on this layer so the XML background color never shows; the glyph sits well inside the central 66 dp safe zone.
- `.../drawable{,-land-*,-port-*}/splash.png` — splash screens at every density/orientation (existing sizes preserved).

## How to regenerate

From `frontend/` (run `npm ci` first if `node_modules` is missing; both scripts
use Playwright's bundled Chromium — no extra dependencies):

```sh
# Icons, splash screens, Play icon + feature graphic (idempotent):
node scripts/generate-store-assets.mjs

# Listing screenshots (builds the production bundle if absent, boots
# `vite preview`, drives the REAL built app against the e2e mock API):
node scripts/generate-store-screenshots.mjs
```

## Synthetic data ONLY in screenshots

Every value visible in every screenshot comes from the synthetic e2e fixtures
(`frontend/e2e/support/mock-api.ts` — "Pat Example", "Dr. Rivera", fabricated
scores/labs). **Never** capture a listing screenshot against a real backend or
with a real name, email, or clinical value (CLAUDE.md §5; Play policy). If a
screenshot needs new content, extend the synthetic scenario in the script — do
not screenshot a live environment.
