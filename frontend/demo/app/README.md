# Self-contained interactive app demo

Builds ONE self-contained HTML file that runs the **real** React app
(`src/App`) entirely in the browser against an in-browser mock API on synthetic
data. No server, no network — open the file and click through patient home,
trends, daily check-in, add data, sources/consent/privacy, about, and the
clinician panel + patient detail.

Output: `dist/neuropathy-demo.html` (~1.8 MB, gitignored — large + regenerable).

## How it works

- `mock.ts` — monkeypatches `window.fetch` **before** React mounts. If a
  request's pathname matches an API route it is fulfilled from the shared
  synthetic fixtures (`src/test/fixtures.ts`), replicating the `method + pathname`
  switch in `e2e/support/mock-api.ts`. Everything else delegates to the real
  fetch. It seeds a restored session (refresh token in `sessionStorage`) so the
  app boots signed-in via the REAL restore flow (`/auth/me` 401 → `/auth/refresh`
  → `/auth/me` 200); login still works if you sign out.
- `demoBar.ts` — a small fixed "Demo" role switcher (Patient / Clinician) mounted
  outside the React root. It sets a role in `localStorage` and reloads; the mock
  then returns the patient `ME` or `CLINICIAN_ME` identity, so the clinician panel
  is reachable.
- `main-demo.tsx` — installs the mock + seeds the session, then renders the REAL
  `<App/>` with the same providers/styles/fonts as `src/main.tsx`. Uses
  **HashRouter** so the single hosted file survives refreshes at any path.
- `vite.demo.config.ts` — a one-file build: `inlineDynamicImports` (no code
  splitting), `cssCodeSplit: false`, and a huge `assetsInlineLimit` so
  fonts/images become data: URIs. Leaves one JS + one CSS asset.
- `build-singlefile.mjs` — post-build Node script (no new npm dep) that folds the
  dist JS + CSS into one HTML at `dist/neuropathy-demo.html`.

## Regenerate

From the `frontend/` directory:

```sh
npx vite build --config demo/app/vite.demo.config.ts   # -> demo/app/dist/{index.html, assets/*}
node demo/app/build-singlefile.mjs                      # -> demo/app/dist/neuropathy-demo.html
```

## Verify (throwaway)

`verify.mjs` (gitignored) drives the built file over `file://` with Playwright
(Chromium preinstalled), asserting each screen renders with ZERO console errors
and saving screenshots to `/tmp/demo-verify/`:

```sh
node demo/app/verify.mjs
```

## Deploying to Vercel (public shareable link)

`frontend/vercel.json` makes a repo connected to Vercel build and serve this demo
as a static site — a public URL anyone can open with **no login** (unlike a
claude.ai artifact). It serves the multi-file build (`dist/index.html` + assets);
the single-file `build-singlefile.mjs` step is NOT needed for hosting.

One-time setup (after `vercel.json` is on the default branch):

1. Sign in to Vercel (the free Hobby plan is enough) → **Add New… → Project** →
   import the GitHub repo.
2. Set **Root Directory** to `frontend`. Leave Build/Output blank — `vercel.json`
   supplies `buildCommand` (`npx vite build --config demo/app/vite.demo.config.ts`)
   and `outputDirectory` (`demo/app/dist`).
3. Deploy. Every push to the production branch rebuilds the demo automatically.
4. If the URL asks visitors to log in, open **Project → Settings → Deployment
   Protection** and set it to **Disabled** (the demo is synthetic-data-only, so a
   public URL is fine).

This Vercel project serves the DEMO (there is no backend yet); a real
app deployment will be a separate project/config once hosting is chosen.

## Caveats

- The EMR "connect" button in Sources starts a SMART-on-FHIR redirect whose
  `authorize_url` points at an external sandbox host (`ehr.example`); under the
  static/HashRouter demo that outbound navigation can't complete, so the live
  EMR round-trip is not exercised. Every other surface is fully interactive.
