# App demo

**[`app-demo.html`](./app-demo.html)** — a single, self-contained walkthrough of the working
app. Open it in any browser (double-click, or send it to someone); no server, no install, no
network. Use ← / → (or the buttons) to move through the screens.

Every screen is a **real screenshot of the built application**, captured running against the
E2E mock-API on **synthetic demo data** — not a mockup, and not real patient information. It
is a product/pitch aid, **not** medical, billing, or legal advice.

## What's in the tour

Login → patient home (improving & declining trends) → trends → daily check-in → add data →
sources/consent/privacy → about → clinician panel → clinician patient detail.

## Regenerating it

The HTML embeds the images, so it is standalone once built. To refresh it after UI changes,
re-capture then re-assemble (from the `frontend/` directory):

```sh
# 1. capture real screens of the built app on mock data (Chromium is pre-installed)
npx playwright test --config demo/playwright.demo.config.ts
# 2. embed them into the single self-contained HTML
node demo/build-demo-html.mjs
```

- Capture tooling lives in [`frontend/demo/`](../../../frontend/demo/) and is **isolated from
  CI** — it uses its own Playwright config (`testDir: ./demo`), so the normal `npm run e2e`
  gate never runs it.
- `frontend/demo/shots/*.png` are intermediate captures and are gitignored (regenerate them;
  don't commit binaries). The committed deliverable is this `app-demo.html`.
- To add, reorder, or re-narrate slides, edit the `SLIDES` array in
  `frontend/demo/build-demo-html.mjs` and re-run step 2.
